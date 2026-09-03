"""Thin adapters over ``bet.api_clients.*`` with a unified return contract.

Every public fetch function here returns a :class:`FetchOutcome` and never
raises: any exception from the underlying client (including
``SportDBMCPError`` and its subclasses, per docs/PIPELINE_SIMPLIFICATION_PLAN.md
section 3) is converted into a ``data_gaps`` entry.

Canonical metric names follow section 5 of the plan: each provider's own
normalization map (``STAT_NAME_MAP`` / ``ALLOWED_STAT_MAP`` / ``STAT_TYPE_MAP``
/ ``SOCCER_STAT_MAP``) is re-aliased here onto one shared vocabulary
(``corners_total``, ``cards_total``, ``shots_total``, ...). A "_total" metric
is always the sum of both sides in one historical match, matching how
STANDARD_MARKET_LINES markets are phrased (e.g. football "Corners Total").
"""
from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from bet.api_clients import get_client
from bet.api_clients.bzzoiro import FINISHED_STATUSES as BZZOIRO_FINISHED_STATUSES
from bet.api_clients.espn import (
    espn_country_pin_words,
    get_espn_league_for_competition,
)
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.sportdb_mcp import SportDBMCPShadowAdapter
from bet.integration.source_result import SourceResultStatus
from bet.simple_stats.contracts import ProviderValue

logger = logging.getLogger(__name__)

# Providers driven by team *name*: each exposes resolve_team_id(name) plus
# get_team_last_fixtures/get_h2h, so one generic loop covers them all.
PROVIDERS_BY_SPORT: dict[str, tuple[str, ...]] = {
    # api-football and understat left this roster on 2026-09-02, measured on
    # that day's slate: each produced 672 data_gap entries and **zero**
    # observations. api-football's account is suspended and answers HTTP 200
    # with an empty ``response`` body, so every lookup resolves to None;
    # understat knows five leagues and answered "no matches" for every team it
    # was asked about. Between them they were 1,344 of the run's 3,579 gaps --
    # noise that reads like missing coverage and is missing entitlement.
    #
    # Their clients, alias tables and fetch functions are kept, unused, exactly
    # as sportdb's were: restoring either is one word in this tuple.
    "football": ("espn-football",),
    # sackmann was removed on 2026-08-28. It reads two GitHub repositories,
    # JeffSackmann/tennis_atp and tennis_wta, and both now 404 -- not the CSVs,
    # the repositories: the GitHub API answers "Not Found" for each, while the
    # account itself is alive and still publishes tennis_MatchChartingProject.
    # The data moved or was withdrawn; where to is not known, and asserting a
    # provider that serves nothing is exactly the mistake the 18 dead ESPN
    # league codes were. It stays in KNOWN_DEAD_PROVIDERS (preflight.py) so the
    # morning check keeps reporting it as dead rather than quietly forgetting
    # it, and its alias table below is kept so restoring it is a one-line
    # change once someone finds where the CSVs went.
    "tennis": ("tennis-abstract", "espn-tennis"),
}

# Providers that cannot be driven by team *name* and are therefore fetched
# through their own dedicated path in enrich.py, keyed off the native ids
# discovery captured (EventRecord.source_ids / .provider_team_ids):
#   highlightly -> /last-five-games, /head-2-head, /statistics/{match_id}
#   bzzoiro     -> /teams/{id}/fixtures, /events/{id}/, /events/{id}/stats/
#
# sportdb (flashscore competition results -> flashscore_get_match_stats) was
# removed from this roster on 2026-08-31: it answered HTTP 402 on 159/159
# requests that day, contributing nothing but ~340 false data_gap entries per
# run. Its client (api_clients/sportdb_mcp.py) and fetch functions below are
# kept, unused, in case the entitlement is restored -- only the active roster
# entry is gone.
#
# bzzoiro-tennis was removed on 2026-09-02, on the operator's decision and on
# the evidence: it has answered HTTP 402 ``addon_required`` since 2026-09-01,
# so on the last slate it ran it contributed **zero observations to 38 tennis
# fixtures** while its absence produced a data_gap on every one of them. Its
# ceiling was 95 calls a day against ~16 an event -- about six fixtures -- so
# even entitled it could never have covered a slate. Client, discovery adapter,
# fetch functions and tests are gone rather than left dormant: a provider that
# is wired in and cannot answer is indistinguishable, in an artifact, from one
# that answered nothing.
NATIVE_ID_PROVIDERS_BY_SPORT: dict[str, tuple[str, ...]] = {
    "football": ("highlightly", "bzzoiro"),
}

# The provider a sport's numbers are *from*, as against the ones that check it.
#
# Football has one: bzzoiro serves 55 canonical metrics per match, unsummed,
# with half-splits and per-team splits, against espn-football's 6 and
# highlightly's 14. Measured on 2026-09-02 over the 287 (match, metric) points
# where bzzoiro and espn-football both reported, the two agreed **exactly** on
# 92-98% of them (mean absolute difference 0.02-0.13): espn-football is a
# second transcription of the same match, not a second measurement of it.
#
# That is what makes it a corroborator and not a source. Its value is the
# check, and a check is only worth running where there is something to check.
#
# **Tennis has no entry, and after 2026-09-02 that is a finding rather than a
# gap.** Its two providers are complementary, not ranked, and neither could
# stand in for the other:
#
#   tennis-abstract  aces, double faults, first-serve %, break points faced,
#                    the surface, and a full career of them -- and no
#                    competition or season id of any kind.
#   espn-tennis      total games and total sets, and nothing else -- but read
#                    off the published set score, which is the quantity those
#                    two markets settle on, plus the tournament id, season and
#                    round that let a sample be scoped at all.
#
# Whichever were named primary, the sheet would lose the half the other holds.
# The one thing they overlap on is total games, and there they now compute the
# same quantity the same way (``api_clients/tennis_score.py``), which is what
# makes their agreement mean something.
PRIMARY_PROVIDER_BY_SPORT: dict[str, str] = {
    "football": "bzzoiro",
}


def corroborators_for(sport: str) -> tuple[str, ...]:
    """Every provider of ``sport`` that is not its primary.

    Reads the two rosters rather than restating them, so a provider added to
    either one cannot be silently left out of the corroboration rule in
    enrich's ``_build_tasks``. A sport with no primary has no corroborators
    either -- there, every provider is a source.
    """
    primary = PRIMARY_PROVIDER_BY_SPORT.get(sport)
    if primary is None:
        return ()
    return tuple(
        p
        for p in (*PROVIDERS_BY_SPORT.get(sport, ()), *NATIVE_ID_PROVIDERS_BY_SPORT.get(sport, ()))
        if p != primary
    )

# google-sports is intentionally not part of PROVIDERS_BY_SPORT: it only
# returns narrative H2H context (score, date, red-card flag), never a numeric
# value for one of our canonical metrics, so it has no slot in
# MetricObservation. fetch_google_sports_h2h() below exists for completeness
# / future use but is not called from enrich.py's metric-fetching loop.

# Six of the twenty-eight stats ESPN parses (SOCCER_STAT_MAP in
# api_clients/espn.py), plus the three added on 2026-09-02. The three were
# already in the client's output and were being dropped here: ESPN publishes
# offsides, red cards and blocked shots on the same /summary payload the other
# six come from, bzzoiro serves all three as canonical metrics, and a
# corroborator that declines to corroborate three metrics it holds is checking
# less than it costs.
#
# Nothing beyond these nine is added, and the omission is deliberate rather
# than pending: passes, crosses, tackles, interceptions, clearances and saves
# have no line in STANDARD_MARKET_LINES, so aliasing them would add a column to
# every dossier that no row ever reads.
_ESPN_FOOTBALL_ALIASES = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "red_cards": "red_cards_total",
    "shots": "shots_total",
    "shots_on_target": "shots_on_target_total",
    "blocked_shots": "blocked_shots_total",
    "fouls": "fouls_total",
    "offsides": "offsides_total",
    "possession": "possession",
}
_API_FOOTBALL_ALIASES = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "shots": "shots_total",
    "shots_on_target": "shots_on_target_total",
    "possession": "possession",
}
_HIGHLIGHTLY_NORMALIZED_ALIASES = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "red_cards": "red_cards_total",
    "shots_on_goal": "shots_on_target_total",
    "shots_off_target": "shots_off_target_total",
    "blocked_shots": "blocked_shots_total",
    "fouls": "fouls_total",
    "offsides": "offsides_total",
    "possession": "possession",
    "expected_goals": "expected_goals_total",
}
_HIGHLIGHTLY_DISPLAY_NAME_ALIASES = {
    "Corners": "corners_total",
    "Yellow cards": "cards_total",
    "Shots on target": "shots_on_target_total",
    "Fouls": "fouls_total",
    "Possession": "possession",
    "Expected Goals": "expected_goals_total",
}
# Bzzoiro is the only provider whose stats survive into the dossier *unsummed*,
# so it needs two tables rather than one.
#
# The match-total table mirrors every other provider: both sides added up, one
# value per historical match, which is how STANDARD_MARKET_LINES phrases
# "Corners Total".
_BZZOIRO_TOTAL_ALIASES = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "red_cards": "red_cards_total",
    "shots": "shots_total",
    "shots_on_target": "shots_on_target_total",
    "shots_off_target": "shots_off_target_total",
    "blocked_shots": "blocked_shots_total",
    "fouls": "fouls_total",
    "offsides": "offsides_total",
    "possession": "possession",
}
# The per-team table is deliberately shorter: it covers exactly the stats that
# have a team market in STANDARD_MARKET_LINES. A "_for" metric nobody can
# price is a column in every artifact that no row ever reads.
#
# "_for", not "_total", because these must not collide. The match total and the
# team's own contribution are different numbers about the same match, every
# other provider can only supply the first, and a run where Bzzoiro quietly
# overwrote corners_total with one side's five corners would report the whole
# slate as DISAGREE while looking like an improvement.
_BZZOIRO_FOR_ALIASES = {
    "corners": "corners_for",
    "yellow_cards": "cards_for",
    "shots": "shots_for",
    "shots_on_target": "shots_on_target_for",
    "fouls": "fouls_for",
    "offsides": "offsides_for",
}


def _bzzoiro_half_alias(full_match_name: str, period: str) -> str:
    """Insert a half-period tag before the trailing ``_total``/``_for``.

    ``"corners_total"`` + ``"1h"`` -> ``"corners_1h_total"`` -- the suffix stays
    last (docs/PLAN_BOGATE_STATYSTYKI.md Faza 3 naming rule) so it is not read
    as a percentage by ``PERCENTAGE_METRICS`` membership.
    """
    for suffix in ("_total", "_for"):
        if full_match_name.endswith(suffix):
            return f"{full_match_name[: -len(suffix)]}_{period}{suffix}"
    return f"{full_match_name}_{period}"


# The bzzoiro client tags a half-split row's normalized_metric_name "<name>_1h"
# / "<name>_2h" (e.g. "corners_1h") -- these route each such row to the same
# canonical half metric ("corners_1h_total" / "corners_1h_for") the full-match
# aliases above build for the whole match.
_BZZOIRO_HALF_PERIODS = ("1h", "2h")
_BZZOIRO_TOTAL_ALIASES_BY_PERIOD = {
    period: {
        f"{raw}_{period}": _bzzoiro_half_alias(total_name, period)
        for raw, total_name in _BZZOIRO_TOTAL_ALIASES.items()
    }
    for period in _BZZOIRO_HALF_PERIODS
}
_BZZOIRO_FOR_ALIASES_BY_PERIOD = {
    period: {
        f"{raw}_{period}": _bzzoiro_half_alias(for_name, period)
        for raw, for_name in _BZZOIRO_FOR_ALIASES.items()
    }
    for period in _BZZOIRO_HALF_PERIODS
}
# Canonical player-prop metrics, keyed by the client's normalized names. The
# client already emits this vocabulary, so this table exists to state which of
# its fields the pipeline prices, not to rename them.
_BZZOIRO_PLAYER_ALIASES = {
    "player_total_shots": "player_total_shots",
    "player_shots_on_target": "player_shots_on_target",
    "player_fouls": "player_fouls",
    "player_was_fouled": "player_was_fouled",
    "player_tackles": "player_tackles",
    "player_assists": "player_assists",
    "player_offsides": "player_offsides",
}
# "Player to be Carded" is a bet on *any* card, so a straight red settles it
# yes. Pricing it off yellows alone would report a carded player as not carded
# in exactly the matches where the card was most obvious, so the two are summed
# into one canonical metric rather than aliased separately. Cards are mutually
# exclusive per shown card, so the sum is the count of cards, never a
# double-count of one.
_BZZOIRO_PLAYER_CARD_KEYS = ("player_yellow_cards", "player_red_cards")
_BZZOIRO_PLAYER_CARDS_METRIC = "player_cards"

_SPORTDB_STATNAME_ALIASES = {
    "Corner Kicks": "corners_total",
    "Corners": "corners_total",
    "Corner kicks": "corners_total",
    "Yellow Cards": "cards_total",
    "Yellow cards": "cards_total",
    "Total shots": "shots_total",
    "Shots": "shots_total",
    "Shots on target": "shots_on_target_total",
    "Fouls": "fouls_total",
    "Ball Possession": "possession",
    "Ball possession": "possession",
}
_UNDERSTAT_ALIASES = {
    "xG": "expected_goals_total",
    "goals": "goals_total",
}
# tennis-abstract / sackmann report one *player's* line for a match as flat
# scalars ({"aces": 4, "service_games": 9, ...}), not the {"home": x, "away": y}
# pairs every football client uses, so they need their own combiner
# (_flat_from_dict_stats) rather than _combined_from_dict_stats.
_TENNIS_MATCH_STAT_ALIASES = {
    "first_serve_pct": "first_serve_pct",
    "break_points_faced": "break_points_faced",
    # Read, not derived. Both are computed by the client from the published set
    # score (``api_clients/tennis_score.py``), which is the quantity the Total
    # Games and Total Sets markets settle on. They used to be derived here from
    # ``service_games + return_games``, which counts every game that had a
    # server and therefore misses the tie-break game in each 7-6 set -- a
    # one-directional shortfall on 98.37% of the tie-break rows in this
    # provider's own cache.
    "total_games": "total_games",
    "total_sets": "total_sets",
    # The queried player's own line. These are the ``_for`` metrics the
    # per-player markets read ("Player Aces", "Player Double Faults", "Player
    # Games Won"), and they used to be served only by bzzoiro-tennis, whose box
    # score arrived already split p1/p2. When that provider was removed on
    # 2026-09-02 the three markets would have gone dark -- except that every
    # tennis-abstract row *is* one player's line, so the figures were there all
    # along and simply had no alias. The provider that replaces them has the
    # full career rather than a 95-a-day allowance.
    #
    # ``games_won`` is derived by the client from the set score plus the row's
    # win/loss marker, and is absent on the rows where those two disagree.
    "aces": "aces_for",
    "double_faults": "double_faults_for",
    "games_won": "games_won",
}
# Canonical "_total" metrics for tennis are both players' figures summed for
# one match, matching how STANDARD_MARKET_LINES phrases "Total Aces". A
# tennis-abstract row holds one player's line plus the opponent's, so the pair
# is summed rather than either half being emitted alone: mapping "aces"
# straight onto aces_total reported roughly half the real match total and made
# every UNDER line look like a 100% hit.
_TENNIS_PAIRED_STAT_KEYS = {
    "aces_total": ("aces", "opponent_aces"),
    "double_faults_total": ("double_faults", "opponent_double_faults"),
}
_TENNIS_ESPN_ALIASES = {
    "games_won": "total_games",
    "sets_won": "total_sets",
}
_FLAT_STAT_PROVIDERS = frozenset({"tennis-abstract", "sackmann"})

_ALIASES_BY_PROVIDER: dict[str, dict[str, str]] = {
    "espn-football": _ESPN_FOOTBALL_ALIASES,
    "espn-tennis": _TENNIS_ESPN_ALIASES,
    "api-football": _API_FOOTBALL_ALIASES,
    "tennis-abstract": _TENNIS_MATCH_STAT_ALIASES,
    "sackmann": _TENNIS_MATCH_STAT_ALIASES,
}

# Providers whose get_team_last_fixtures needs the *_result variant unwrapped
# from a SourceOperationResult (the plain method is a bare id-only stub).
_LAST_FIXTURES_METHOD: dict[str, tuple[str, bool]] = {
    "api-football": ("get_team_last_fixtures_result", True),
}
_DEFAULT_LAST_FIXTURES_METHOD = ("get_team_last_fixtures", False)

# Providers whose last-fixtures call can be restricted to one draw, and the
# code they name the Grand Slam main draw with.
#
# Only tennis-abstract, and only because its cache is the player's whole
# career off a single scrape -- choosing which of those matches to read costs
# no requests. espn-tennis is deliberately absent: its route is per season and
# already returns the year, so its Grand Slam rows are in the sample without
# asking, and asking would cost calls it has no cheap answer for.
#
# Why it is needed at all: the draw rule in ``scope_values`` can only keep
# observations that reached the dossier, and a chronological last-ten reaches
# almost none. An ATP player's last ten matches in September are Cincinnati,
# Winston-Salem and Challengers; on the 2026-09-03 slate the fifteen men's
# dossiers held 170 aces observations and not one came from a Grand Slam,
# while those same players' caches held between 51 and 201 Slam matches each.
# Scoping without this is a correct filter over a sample that cannot answer.
_DRAW_FILTERED_PROVIDERS = {"tennis-abstract": "G", "sackmann": "G"}


def _draw_filter_kwargs(provider: str, competition: str) -> dict[str, str]:
    """``{"level": "G"}`` when tonight is best-of-five and the provider can.

    Empty for every other provider and every other competition, so the
    last-fixtures call is byte-for-byte the one it was before this existed.
    """
    level = _DRAW_FILTERED_PROVIDERS.get(provider)
    if not level:
        return {}
    if tennis_match_format_for_competition(competition) != "BO5":
        return {}
    return {"level": level}

# H2H is only wired for providers whose get_h2h returns a flat, normalized
# meeting shape ({"id"/"fixture_id", "date", ...}). api-football's get_h2h
# returns raw provider payload items nested under "fixture", which this
# generic path does not attempt to parse (section 4.1: api-football is a
# supplementary cross-check, not a primary H2H source).
_H2H_SUPPORTED_PROVIDERS = frozenset({"espn-football", "espn-tennis", "tennis-abstract"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Per-provider run ceilings that override RunBudget's shared default.
#
# One number for every provider was fine while they all had roughly the same
# quota. It stops being fine with bzzoiro in the roster: at the shared default of
# 100 it would run dry after three or four events -- the exact 6-events-of-181
# outcome this provider was added to fix.
#
# Since the PRO upgrade the football product publishes no daily ceiling at all
# (see API_DAILY_LIMITS), so this is the *only* remaining bound on it, and its
# purpose has changed: it is no longer rationing a scarce allowance, it is
# stopping a bug that loops from spending an afternoon on it. 20000 is therefore
# set where it cannot bind a real day -- at ~30 calls an event that is over 600
# fixtures, against 150-180 discovered -- while still terminating a runaway.
RUN_BUDGET_OVERRIDES: dict[str, int] = {"bzzoiro": 20000}


class RunBudget:
    """In-memory per-run call counter, shared across one ENRICH run's
    ThreadPoolExecutor workers (section 7): SerpAPI's GoogleSportsClient
    already bakes in its own MAX_QUERIES_PER_RUN=15; Highlightly and SportDB
    have no such limiter, so the same "counter per-run + RateLimiter
    underneath" pattern is applied here, default 100 calls/run/provider.

    ``RUN_BUDGET_OVERRIDES`` raises that default for providers whose real
    allowance is orders of magnitude larger. The shared default still applies to
    everything not named there, so adding a provider does not silently uncap it.
    """

    def __init__(self, limit: int = 100, overrides: dict[str, int] | None = None):
        self.limit = limit
        self._overrides = dict(RUN_BUDGET_OVERRIDES if overrides is None else overrides)
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def limit_for(self, provider: str) -> int:
        # max(), not a plain lookup: an operator who passes a budget above the
        # override meant to raise the ceiling, not to lower this provider's.
        return max(self.limit, self._overrides.get(provider, 0))

    def try_consume(self, provider: str) -> bool:
        with self._lock:
            used = self._counts.get(provider, 0)
            if used >= self.limit_for(provider):
                return False
            self._counts[provider] = used + 1
            return True


@dataclass
class FetchOutcome:
    """canonical_name -> observed ProviderValue list, plus any data_gap messages."""

    metrics: dict[str, list[ProviderValue]] = field(default_factory=dict)
    data_gaps: list[str] = field(default_factory=list)

    def add(self, canonical_name: str, value: ProviderValue) -> None:
        self.metrics.setdefault(canonical_name, []).append(value)

    def merge(self, other: FetchOutcome) -> None:
        for name, values in other.metrics.items():
            self.metrics.setdefault(name, []).extend(values)
        self.data_gaps.extend(other.data_gaps)


def _field(fx: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(fx, dict):
            if fx.get(name) is not None:
                return fx[name]
        elif hasattr(fx, name) and getattr(fx, name) is not None:
            return getattr(fx, name)
    return default


def _opponent_of(fixture: Any, team_id: str) -> str | None:
    """Whichever side of ``fixture`` is not ``team_id``, or None if unknowable.

    Returning None rather than guessing is the point. The previous shape --
    "if the home id matches, the opponent is away; otherwise the opponent is
    home" -- has no failure case: a row that identifies neither side still
    yields a confident answer, and that answer is the player himself whenever
    he was listed first.

    espn-tennis hit exactly that. Its ``team_id`` is a numeric ESPN athlete id
    while its history rows carried only two display names, so the id comparison
    could never be true, the name comparison could never be true, and every
    match in which ESPN listed the player as competitor[0] was recorded with
    the player as his own opponent. Half of every tennis L10, silently.

    Both halves are now fixed: espn.py emits the participant ids (they were
    always in the payload, just dropped on the floor), and a row that still
    cannot say which side the player was on is refused rather than assumed.
    """
    wanted = str(team_id)
    home_id = _field(fixture, "home_participant_id", "home_team_id")
    away_id = _field(fixture, "away_participant_id", "away_team_id")
    home_team = _field(fixture, "home_team")
    away_team = _field(fixture, "away_team")
    # Ids first: a name can be spelled several ways, an id cannot. Empty
    # strings are "not stated" -- NormalizedFixture defaults both id fields to
    # "" -- and must not be allowed to match an empty team_id.
    for mine, theirs in ((home_id, away_team), (away_id, home_team)):
        if mine not in (None, "") and str(mine) == wanted:
            return theirs
    for mine, theirs in ((home_team, away_team), (away_team, home_team)):
        if mine not in (None, "") and str(mine) == wanted:
            return theirs
    return None


def _side_of(fixture: Any, team_id: str) -> str | None:
    """"home"/"away"/None for whichever side of ``fixture`` is ``team_id``.

    Same id fields ``_opponent_of`` reads, kept as a separate lookup because a
    goals row needs to know *which* side it was, not just who the other side
    was.
    """
    wanted = str(team_id)
    home_id = _field(fixture, "home_participant_id", "home_team_id")
    away_id = _field(fixture, "away_participant_id", "away_team_id")
    if home_id not in (None, "") and str(home_id) == wanted:
        return "home"
    if away_id not in (None, "") and str(away_id) == wanted:
        return "away"
    return None


def _parse_espn_score(score: Any) -> tuple[float, float] | tuple[None, None]:
    """espn.py's ``get_team_last_fixtures_result`` emits ``score`` as the
    literal string ``"{home_score}-{away_score}"`` (or ``""`` if neither side
    reported), never as two separate fields -- so this splits rather than
    reads a shape that does not exist."""
    if not isinstance(score, str) or "-" not in score:
        return None, None
    home_str, _, away_str = score.partition("-")
    try:
        return float(home_str), float(away_str)
    except ValueError:
        return None, None


def _combined_from_dict_stats(stats: dict, aliases: dict[str, str]) -> dict[str, float]:
    """Sum home+away for each aliased raw key of a {"home":x,"away":y}-shaped stats dict."""
    out: dict[str, float] = {}
    if not isinstance(stats, dict):
        return out
    for raw_key, sides in stats.items():
        canonical = aliases.get(raw_key)
        if canonical is None or not isinstance(sides, dict):
            continue
        home = sides.get("home")
        away = sides.get("away")
        if home is None or away is None:
            continue
        try:
            out[canonical] = float(home) + float(away)
        except (TypeError, ValueError):
            continue
    return out


def _flat_from_dict_stats(stats: dict, aliases: dict[str, str]) -> dict[str, float]:
    """Canonical totals from a flat, single-player stats dict (tennis).

    ``total_games`` and ``total_sets`` arrive already computed from the match's
    published set score and are simply aliased through. They used to be derived
    here from ``service_games + return_games``; see the note on
    ``_TENNIS_MATCH_STAT_ALIASES`` for why that was wrong, and by exactly how
    much. A row whose score could not be parsed now contributes neither, rather
    than contributing a figure that is reliably one game low per tie-break.
    """
    out: dict[str, float] = {}
    if not isinstance(stats, dict):
        return out
    for raw_key, canonical in aliases.items():
        value = stats.get(raw_key)
        if value is None or isinstance(value, str):
            continue
        try:
            out[canonical] = float(value)
        except (TypeError, ValueError):
            continue

    for canonical, (own_key, opponent_key) in _TENNIS_PAIRED_STAT_KEYS.items():
        own, opponent = stats.get(own_key), stats.get(opponent_key)
        if own is None or opponent is None:
            continue
        try:
            out[canonical] = float(own) + float(opponent)
        except (TypeError, ValueError):
            continue

    return out


def _combine_stats(provider_key: str, stats: dict, aliases: dict[str, str]) -> dict[str, float]:
    """Pick the right combiner for a provider's stats-dict shape."""
    if provider_key in _FLAT_STAT_PROVIDERS:
        return _flat_from_dict_stats(stats, aliases)
    return _combined_from_dict_stats(stats, aliases)


# A finished football match cannot have zero fouls, and cannot have zero of
# every counted stat at once. Some providers -- espn-football in the lower
# English leagues, measured 2026-08-28 -- publish a fixture they hold no stats
# for as an explicit 0.0 instead of omitting the metric. A zero that means
# "unknown" is worse than no observation at all: it collapses onto the same
# (bucket, day) as a real value from another provider and wins, dragging the
# whole sample toward zero. One day's measurement: 35 such zeros in each of
# corners_total, fouls_total and shots_on_target_total, from 19 fixtures, which
# put median 0.0 on rows the market priced around 10.
_ZERO_IMPOSSIBLE_MARKETS = frozenset({"fouls_total", "fouls_for"})

# Counted-play metrics: a finished football match produces some of each. Goals,
# cards and red cards are deliberately **not** here -- zero of any of those is
# an ordinary result, and it is precisely a real 0-0 that let the old all-values
# test through (see ``_is_absent_not_zero``).
_PLAY_METRICS = frozenset(
    {
        "shots_total",
        "shots_on_target_total",
        "shots_off_target_total",
        "corners_total",
        "fouls_total",
        "offsides_total",
        "shots_for",
        "shots_on_target_for",
        "corners_for",
        "fouls_for",
        "offsides_for",
    }
)

# Orderings no real match can violate: you cannot score more goals than you put
# on target, and you cannot put more on target than you took shots.
#
# This is arithmetic, not a judgement about what is rare, which is what makes it
# a safe filter. The payload that provoked it -- highlightly on match
# 1328313068, in the 2026-09-01 dossier -- reported **six goals with zero shots
# and zero shots on target**, and passed every existing gate: not all its values
# were zero (it had goals and cards), and it carried no fouls key for
# ``_ZERO_IMPOSSIBLE_MARKETS`` to catch. bzzoiro produced one of the same shape
# on 2026-08-31, so this is a class of upstream fault rather than one provider's
# quirk.
#
# ``_ORDERING_TOLERANCE`` of 1 is for own goals: some feeds do not attribute an
# own goal to the scoring side as a shot on target, so goals can legitimately
# exceed shots on target by one. Two is not an accounting convention.
_IMPOSSIBLE_ORDERINGS = (
    ("goals_total", "shots_on_target_total"),
    ("shots_on_target_total", "shots_total"),
    ("goals_for", "shots_on_target_for"),
    ("shots_on_target_for", "shots_for"),
)
_ORDERING_TOLERANCE = 1.0

# Every provider that serves tennis, including the id-addressed one -- the
# retirement test is about the sport, not about how the fixture was looked up.
_TENNIS_PROVIDERS = frozenset(
    {*PROVIDERS_BY_SPORT["tennis"], *NATIVE_ID_PROVIDERS_BY_SPORT.get("tennis", ()), "sackmann"}
)

# A completed singles match cannot be shorter than 6-0 6-0, which is twelve
# games and two sets. Anything under that is a retirement, a walkover or a
# match still in progress -- and a retirement is exactly the shape that flatters
# an UNDER: a player who quits at 2-1 down contributes three games and one ace
# to a "total games UNDER 21.5" sample as though he had played a whole match.
# tennis-abstract already drops rows scored "W/O", but a mid-match retirement
# carries a real score line and passes that filter.
_TENNIS_MIN_COMPLETED_GAMES = 12.0
_TENNIS_MIN_COMPLETED_SETS = 2.0


def _tennis_match_unfinished(provider_key: str, stats: dict) -> bool:
    """Whether the provider itself says this match did not finish.

    Both tennis clients now parse the published score line, and both write a
    ``completed`` flag onto the stats dict from it. That is a stated fact where
    the thresholds above are an inference, and the inference has a hole a
    threshold cannot close: a retirement at 7-6 6-7 1-0 is twenty-seven games
    and three sets, so it clears both bars and enters a Total Games sample as
    though it were a full match -- while being exactly the shape that flatters
    an UNDER.

    The thresholds stay as the fallback for a payload that states nothing.
    """
    if provider_key not in _TENNIS_PROVIDERS:
        return False
    completed = stats.get("completed")
    return completed is False


def _is_absent_not_zero(combined: dict[str, float], provider_key: str = "") -> bool:
    """Whether a stats payload describes something no completed match can be."""
    if not combined:
        return False
    if provider_key in _TENNIS_PROVIDERS:
        sets_played = combined.get("total_sets")
        if sets_played is not None and sets_played < _TENNIS_MIN_COMPLETED_SETS:
            return True
        games = combined.get("total_games")
        if games is not None and games < _TENNIS_MIN_COMPLETED_GAMES:
            return True
        return len(combined) >= 2 and all(value == 0.0 for value in combined.values())
    if any(combined.get(market) == 0.0 for market in _ZERO_IMPOSSIBLE_MARKETS):
        return True
    # Internally impossible: goals it cannot have scored, or shots on target it
    # cannot have taken. See _IMPOSSIBLE_ORDERINGS.
    for greater, lesser in _IMPOSSIBLE_ORDERINGS:
        big, small = combined.get(greater), combined.get(lesser)
        if big is not None and small is not None and big > small + _ORDERING_TOLERANCE:
            return True
    # Every *counted-play* metric present is zero. Restricted to those, rather
    # than to every value in the payload, because a real 0-0 draw with absent
    # shot data satisfied "all values are zero" only by accident -- add one card
    # to the same payload and it passed.
    play = [combined[market] for market in combined if market in _PLAY_METRICS]
    if len(play) >= 2 and all(value == 0.0 for value in play):
        return True
    return len(combined) >= 2 and all(value == 0.0 for value in combined.values())


def _id_or_none(raw: Any) -> str | None:
    """A provider id as a string, or None when the provider did not give one.

    Empty string and ``"None"`` both collapse to None: ANALYZE's scope filter
    treats None as "cannot tell, keep it", and a row carrying the literal text
    ``"None"`` would instead group with every other row that failed the same
    way -- an invented competition shared by unrelated matches.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


# Providers whose "which side" answer means a *venue*. The tennis ones are
# excluded on purpose: ``_side_of`` there resolves which participant slot a
# player occupied in the draw, which is not a venue -- neither player is at
# home at a neutral tournament. Recording slot one as "home" would be the same
# class of invented fact as the ordering violations ``_is_absent_not_zero``
# refuses.
_VENUE_BEARING_PROVIDERS = frozenset(PROVIDERS_BY_SPORT["football"]) | frozenset(
    NATIVE_ID_PROVIDERS_BY_SPORT["football"]
)


def _venue_or_none(provider: str, side: str | None) -> str | None:
    """``side`` as a venue, or None when it is not one.

    One gate rather than a check at each of the six call sites that have a
    side to hand: a provider added to the tennis list later must not start
    emitting venues because somebody forgot the distinction.
    """
    if side not in ("home", "away"):
        return None
    return side if provider in _VENUE_BEARING_PROVIDERS else None


# Providers whose historical rows carry a surface, and how each one carries it.
#
# ``tennis-abstract`` states it per match (``surf``). ``espn-tennis`` does not
# state it at all -- but it states the *tournament*, and the tournament is what
# a surface is a property of, so its rows are resolved through the same table
# ANALYZE pins tonight's fixture with.
#
# Until 2026-09-02 espn-tennis was simply in neither camp, and the consequence
# was not "no surface information": it was **immunity from the surface
# filter**. ``scope_values`` drops an observation only when both the fixture's
# surface and the observation's are known, so a provider that never states one
# cannot lose a row. Measured on that day's slate -- 38 fixtures, every one of
# them pinned Hard -- tennis-abstract lost 145 of its 522 ``total_games``
# observations to the filter (27.8%) while espn-tennis lost 0 of 478, and the
# provider that had just been shown to undercount games went from 47.8% of the
# raw pool to 55.9% of the scoped one. A filter that can only ever fire on one
# of two providers reweights the sample toward the other.
_SURFACE_BEARING_PROVIDERS = frozenset({"tennis-abstract", "sackmann", "espn-tennis"})

# Providers whose rows name the tournament rather than the surface, and are
# therefore resolved through ``config/tennis_surface_map.json``.
_COMPETITION_SURFACED_PROVIDERS = frozenset({"espn-tennis"})

_TENNIS_SURFACE_MAP_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "tennis_surface_map.json"
)
_TENNIS_SURFACE_MAP_CACHE: dict[str, str] | None = None
_TENNIS_SURFACE_MAP_LOCK = threading.Lock()


def tennis_surface_for_competition(competition: str | None) -> str | None:
    """``"Hard"``, ``"Clay"``, ``"Grass"``, or None when the name is unpinned.

    One table, one loader, two callers: ANALYZE asks it what surface tonight's
    fixture is on, and this module asks it what surface a historical ESPN row
    was on. They meet in a ``!=`` inside ``scope_values``, so answering them
    from two tables would be a way to silently delete every observation.

    None is not a guess and never becomes one. An unlisted tournament filters
    nothing, exactly as it did before the config existed.
    """
    global _TENNIS_SURFACE_MAP_CACHE
    with _TENNIS_SURFACE_MAP_LOCK:
        cache = _TENNIS_SURFACE_MAP_CACHE
    if cache is None:
        try:
            document = json.loads(_TENNIS_SURFACE_MAP_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            document = {}
        surfaces = document.get("surfaces") if isinstance(document, dict) else {}
        if not isinstance(surfaces, dict):
            surfaces = {}
        # Normalised through ``_KNOWN_SURFACES`` on the way in, for the same
        # reason the values coming off a provider row are: a config pin spelled
        # "hard" would mismatch every correctly-surfaced observation and keep
        # only the surface-unknown ones -- the exact inversion of the intent.
        cache = {
            str(name): canonical
            for name, value in surfaces.items()
            if (canonical := _KNOWN_SURFACES.get(str(value).strip().lower()))
        }
        with _TENNIS_SURFACE_MAP_LOCK:
            if _TENNIS_SURFACE_MAP_CACHE is None:
                _TENNIS_SURFACE_MAP_CACHE = cache
            cache = _TENNIS_SURFACE_MAP_CACHE
    return cache.get(competition or "")

# The three surfaces professional tennis is played on, normalised to the
# spelling ``config/tennis_surface_map.json`` uses. Anything else -- "Carpet",
# a blank, a stray code -- becomes None rather than a fourth category, on the
# same rule as ``_venue_or_none``: a value we cannot place must read as "not
# stated", never as a surface that happens to differ from tonight's.
_KNOWN_SURFACES = {"hard": "Hard", "clay": "Clay", "grass": "Grass"}


def reset_tennis_surface_cache() -> None:
    """Forget the cached surface table. For tests only."""
    global _TENNIS_SURFACE_MAP_CACHE
    with _TENNIS_SURFACE_MAP_LOCK:
        _TENNIS_SURFACE_MAP_CACHE = None


# Providers whose historical rows say which draw a match belonged to, and how.
#
# ``tennis-abstract`` states it per match (``level``, "G" for Grand Slam) on
# all 78,750 of its cached rows. ``espn-tennis`` does not state it -- but it
# names the *tournament*, and a draw is a property of a tournament, so its rows
# go through the same pin ANALYZE reads the fixture's own format from.
#
# The reason both are listed and neither is trusted alone is the surface rule's
# lesson, one file up: a filter that can only ever fire on one of two providers
# does not merely lose information, it reweights the sample toward the other.
_MATCH_LEVEL_BEARING_PROVIDERS = frozenset(
    {"tennis-abstract", "sackmann", "espn-tennis"}
)

# Providers whose rows name the tournament rather than the draw, and are
# therefore resolved through ``config/tennis_match_format.json``.
_COMPETITION_LEVELLED_PROVIDERS = frozenset({"espn-tennis"})

# tennis-abstract's ``level`` column, mapped onto the two draw classes that
# matter. "G" is the Grand Slam main draw; M (Masters), A (ATP/WTA tour), C
# (Challenger), S (satellite), F (tour finals) and the ITF prize-money tiers
# 25/15 are all best-of-three events today.
#
# D (Davis Cup) and O (Olympics) are deliberately absent, and absent means
# None. Both were best-of-five within living memory -- Davis Cup rubbers until
# 2018, the Olympic men's final until 2012 -- and a code we will not commit to
# must read as "not stated", never as a draw that happens to differ from
# tonight's. Inside the 500-day observation window this costs nothing; it is
# here so that widening that window cannot quietly turn a wrong assertion into
# deleted observations.
_KNOWN_MATCH_LEVELS = {
    "g": "GRAND_SLAM",
    "gq": "GRAND_SLAM_QUALIFYING",
    "m": "TOUR",
    "a": "TOUR",
    "c": "TOUR",
    "s": "TOUR",
    "f": "TOUR",
    "25": "TOUR",
    "15": "TOUR",
}

# Grand Slam *qualifying* is best-of-three -- at all four tournaments, on both
# tours -- and tennis-abstract files it under the same ``level`` "G" as the
# main draw. Only the round column separates them.
#
# Found by reading the sample the fetch filter built rather than the code: four
# of the six matches it selected for Blockx-Trungelliti were Q1/Q2/Q3, and two
# of four for Svajda-Gea. Left in, they would have been the same defect this
# whole change exists to remove -- best-of-three counts priced against a
# best-of-five ladder -- arriving by a new route and wearing the label
# GRAND_SLAM.
#
# "QF" is a quarter-final and must not match: the pattern is Q followed by a
# digit, and ESPN spells the same thing out in words.
_QUALIFYING_ROUND = re.compile(r"^\s*(?:q\d|qual)", re.IGNORECASE)

_TENNIS_FORMAT_MAP_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "tennis_match_format.json"
)
_TENNIS_FORMAT_MAP_CACHE: dict[str, str] | None = None
_TENNIS_FORMAT_MAP_LOCK = threading.Lock()


def tennis_match_format_for_competition(competition: str | None) -> str | None:
    """``"BO5"``, ``"BO3"``, or None when the name is unpinned.

    One table, one loader, two callers -- the arrangement
    ``tennis_surface_for_competition`` already documents and for the same
    reason. ANALYZE asks it what format tonight's fixture is played to, and
    this module asks whether a historical ESPN row was a Grand Slam match; the
    two answers meet inside ``scope_values``, so they have to come from one
    read of one file.

    None is not a guess and never becomes one. An unpinned tournament gates
    nothing, exactly as it did before the config existed.
    """
    global _TENNIS_FORMAT_MAP_CACHE
    with _TENNIS_FORMAT_MAP_LOCK:
        cache = _TENNIS_FORMAT_MAP_CACHE
    if cache is None:
        try:
            document = json.loads(_TENNIS_FORMAT_MAP_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            document = {}
        formats = document.get("formats") if isinstance(document, dict) else {}
        if not isinstance(formats, dict):
            formats = {}
        cache = {str(name): str(value) for name, value in formats.items()}
        with _TENNIS_FORMAT_MAP_LOCK:
            if _TENNIS_FORMAT_MAP_CACHE is None:
                _TENNIS_FORMAT_MAP_CACHE = cache
            cache = _TENNIS_FORMAT_MAP_CACHE
    return cache.get(competition or "")


def reset_tennis_match_format_cache() -> None:
    """Forget the cached format table. For tests only."""
    global _TENNIS_FORMAT_MAP_CACHE
    with _TENNIS_FORMAT_MAP_LOCK:
        _TENNIS_FORMAT_MAP_CACHE = None


def _match_level_or_none(provider: str, level: Any) -> str | None:
    """``ProviderValue.match_level`` for one observation, or None.

    Mirrors ``_surface_or_none``: the caller passes whatever its provider said
    and this decides whether the field may be set at all. A football provider
    passing something truthy still records None -- a football "draw class" is
    a fact nobody measured.
    """
    if provider not in _MATCH_LEVEL_BEARING_PROVIDERS:
        return None
    if not isinstance(level, str):
        return None
    return _KNOWN_MATCH_LEVELS.get(level.strip().lower())


def _row_match_level(provider: str, stats: dict, fixture: Any) -> Any:
    """What a provider row says about its draw, however it says it.

    Two spellings of one fact, kept together so no caller has to know which
    provider it holds: the row's own ``level`` code where there is one, and
    otherwise the tournament the row names.

    Grand Slam *qualifying* is best-of-three and tennis-abstract files it under
    the same ``level`` as the main draw, so the round is read too and those rows
    come back as their own class -- see ``_QUALIFYING_ROUND``.

    A tournament pinned in ``config/tennis_match_format.json`` is a Grand Slam
    -- every one of its ten entries is, by that file's own ``_scope``, because
    men's Grand Slam main-draw singles is the whole of best-of-five in the
    professional game and the WTA halves are listed only so that a checked
    competition is distinguishable from an unchecked one.
    ``test_every_pinned_name_is_a_grand_slam`` is where that inference breaks
    if a best-of-three event is ever added to the table.

    An unpinned name returns None and is *not* read as a tour event, even
    though ESPN spells its four slams exactly as the table pins them (verified
    2026-09-03 against the cached fixture rows, which carry names like "ATP US
    Open" beside "ATP National Bank Open presented by Rogers"). Asserting
    "tour" from a name we do not recognise would make a slam we failed to spell
    into deleted best-of-five observations, and deleting real observations is
    worse than admitting we cannot place them: unknown still leaves the sample,
    but it leaves under a reason that says so, and ``_share_within_a_match``
    can still recover it from tennis-abstract's ``level`` for the same match.
    """
    round_name = stats.get("round") if isinstance(stats, dict) else None
    if round_name is None:
        round_name = _field(fixture, "round", "round_name", default="")
    qualifying = bool(_QUALIFYING_ROUND.match(str(round_name or "")))

    stated = stats.get("level") if isinstance(stats, dict) else None
    if stated:
        if str(stated).strip().upper() == "G" and qualifying:
            return "GQ"
        return stated
    if provider not in _COMPETITION_LEVELLED_PROVIDERS:
        return None
    name = _field(fixture, "competition_name", default="")
    if tennis_match_format_for_competition(name) is None:
        return None
    return "GQ" if qualifying else "G"


def _surface_or_none(provider: str, surface: Any) -> str | None:
    """``ProviderValue.surface`` for one observation, or None.

    Mirrors ``_venue_or_none``: the caller passes whatever its provider said
    and this decides whether the field may be set at all. A football provider
    passing something truthy still records None -- the field is tennis-only by
    construction, and a football "surface" would be a fact nobody measured.
    """
    if provider not in _SURFACE_BEARING_PROVIDERS:
        return None
    if not isinstance(surface, str):
        return None
    return _KNOWN_SURFACES.get(surface.strip().lower())


def _row_surface(provider: str, stats: dict, fixture: Any) -> Any:
    """What a provider row says about its surface, however it says it.

    Two spellings of the same fact, kept in one place so a caller never has to
    know which provider it is holding: the row's own ``surface`` field where
    there is one, and otherwise the tournament the row names, looked up in the
    surface table.
    """
    stated = stats.get("surface") if isinstance(stats, dict) else None
    if stated:
        return stated
    if provider not in _COMPETITION_SURFACED_PROVIDERS:
        return None
    return tennis_surface_for_competition(_field(fixture, "competition_name", default=""))


def _make_values(
    provider: str,
    match_id: Any,
    match_date: str,
    opponent: str,
    combined: dict[str, float],
    *,
    competition_id: Any = None,
    season_id: Any = None,
    side: str | None = None,
    surface: Any = None,
    match_level: Any = None,
) -> dict[str, ProviderValue]:
    """One ProviderValue per canonical metric in ``combined``.

    ``competition_id``/``season_id`` are the provider's own ids for the
    historical match, passed by the call sites that have them and left None by
    those that do not. They are carried, never interpreted here: deciding
    whether a competition belongs in a sample is ANALYZE's job (see
    ``scope_values``), and doing it at ingest would bake one run's judgement
    into the dossier with no way to audit it afterwards.

    ``side`` is which side of that historical match the team whose bucket this
    is played on -- the same value the call site already computed to split the
    match's stats between the two teams. It becomes ``ProviderValue.venue``
    only for a football provider (see ``_venue_or_none``); everything else
    records None, which downstream reads as "not stated" and never as "away".
    """
    if not _is_recent(match_date):
        return {}
    observed_at = _now_iso()
    competition = _id_or_none(competition_id)
    season = _id_or_none(season_id)
    venue = _venue_or_none(provider, side)
    surface_name = _surface_or_none(provider, surface)
    level = _match_level_or_none(provider, match_level)
    return {
        name: ProviderValue(
            provider=provider,
            match_id=str(match_id),
            match_date=match_date or "",
            opponent=opponent or "unknown",
            value=float(val),
            observed_at=observed_at,
            competition_id=competition,
            season_id=season,
            venue=venue,
            surface=surface_name,
            match_level=level,
        )
        for name, val in combined.items()
    }


def normalize_highlightly_statistics(raw_payload: dict) -> dict[str, float]:
    """Normalize a raw Highlightly ``/statistics`` capture (see
    tests/fixtures/reports/football_data_foundation/live_response_corpus) into
    canonical_name -> combined (home+away) totals."""
    sums: dict[str, float] = {}
    body = raw_payload.get("body") if isinstance(raw_payload, dict) else raw_payload
    if not isinstance(body, list):
        return sums
    for team_block in body:
        if not isinstance(team_block, dict):
            continue
        for stat in team_block.get("statistics", []):
            if not isinstance(stat, dict):
                continue
            canonical = _HIGHLIGHTLY_DISPLAY_NAME_ALIASES.get(stat.get("displayName", ""))
            if canonical is None:
                continue
            try:
                value = float(stat.get("value"))
            except (TypeError, ValueError):
                continue
            sums[canonical] = sums.get(canonical, 0.0) + value
    return sums


def _parse_sportdb_number(raw: Any) -> float | None:
    """SportDB stat values are strings, and not always bare numbers: possession
    arrives as ``"48%"`` and passes as ``"83% (372/450)"`` (verified live
    2026-08-25). Take the leading numeric token and drop any ``%``/parenthetical
    tail rather than letting float() raise and silently lose the metric."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    match = re.match(r"^-?\d+(?:\.\d+)?", text.replace(",", "."))
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalize_sportdb_match_stats(raw_result: dict) -> dict[str, float]:
    """Normalize a raw SportDB ``flashscore_get_match_stats`` payload into
    canonical_name -> combined (home+away) totals. Only the "Match" (full
    match) period is used, not per-half splits.

    The period list lives under ``data`` in the live MCP response and under
    ``body`` in the REST captures stored in
    tests/fixtures/.../live_response_corpus; both are accepted, because reading
    only ``body`` made this function return ``{}`` for every real run while
    still passing its fixture-based tests.
    """
    sums: dict[str, float] = {}
    if not isinstance(raw_result, dict):
        return sums
    periods = raw_result.get("data")
    if not isinstance(periods, list):
        periods = raw_result.get("body")
    if not isinstance(periods, list):
        return sums

    for period in periods:
        if not isinstance(period, dict) or period.get("period") != "Match":
            continue
        # Real captures repeat the same statName within one period (verified
        # against live_response_corpus's Norway-Senegal match_stats.json, e.g.
        # "Corner kicks" appears twice under "Match"); keep only the last
        # value per statName so a repeated row never doubles the total.
        by_stat_name: dict[str, tuple[float, float]] = {}
        for stat in period.get("stats", []):
            if not isinstance(stat, dict):
                continue
            canonical = _SPORTDB_STATNAME_ALIASES.get(stat.get("statName", ""))
            if canonical is None:
                continue
            home = _parse_sportdb_number(stat.get("homeValue"))
            away = _parse_sportdb_number(stat.get("awayValue"))
            if home is None or away is None:
                continue
            by_stat_name[canonical] = (home, away)
        for canonical, (home, away) in by_stat_name.items():
            sums[canonical] = sums.get(canonical, 0.0) + home + away
    return sums


class ProviderLeagueUnsupported(RuntimeError):
    """This provider has no data surface for this competition.

    Raised instead of returning a differently-scoped client, because the
    fallback was worse than the failure: ``get_client("espn-football")`` is
    pinned to ``eng.1``, so an unmapped competition sent 'Abha Club' into a
    Premier League team search. That either finds nothing (a data_gap blaming
    the team name for a league problem) or, for a name close enough to an
    English club, silently answers with the wrong club's season -- the same
    defect class as sportdb serving FC Basel's results for Saudi fixtures.
    """


# league code -> what ESPN's /teams actually returned for it. Populated by
# probing, never hand-authored: the set of leagues ESPN gives a team directory
# to is ESPN's business and changes without notice, so a literal list here
# would be a guess that rots. One probe per league per process, memoised
# because ENRICH runs its providers on a thread pool and would otherwise probe
# once per fixture.
_ESPN_TEAM_DIRECTORY: dict[str, _ESPNDirectory] = {}
_ESPN_TEAM_DIRECTORY_LOCK = threading.Lock()


@dataclass(frozen=True)
class _ESPNDirectory:
    """What ESPN's /teams says about a league code.

    ``league_name`` is ESPN's own name for the code and is the only
    provider-side evidence available about *which* league a pin actually
    points at, which is what makes _espn_pin_contradicted possible.
    """

    served: bool
    league_name: str = ""
    team_count: int = 0

    @property
    def usable(self) -> bool:
        # A 200 with an empty team list is not a directory. ESPN answers that
        # way for retired and never-populated codes -- verified 2026-08-28:
        # cze.1 ("Gambrinus Liga"), fin.1 ("Finnish Veikkausliga"), usa.w.1
        # ("USA Women's United Soccer Association") and irl.1 ("Irish Premier
        # Division") all return 200 with zero teams. Treating 200 as success
        # let all four past this gate, and resolve_team_id then failed with
        # "could not resolve team identity for '<club>'" -- the team-name
        # blame this gate exists to prevent.
        return self.served and self.team_count > 0


# The words that make a pin checkable against ESPN's own league name are the
# resolver's words, composed onto the country -> code-prefix map next to them
# (ESPN_COUNTRY_CODE_PREFIXES in api_clients/espn.py). This used to be a second
# hand-kept list, and it had drifted: 24 spellings the resolver folds --
# "osterreich", "ecuadorian", "italiana", "danmark", "brasil" and the rest --
# were words this gate did not know. That is not a wrong answer, it is silence,
# and silence here reads as a pass. Deriving the list means the safety net can
# no longer be thinner than the resolver that feeds it.
#
# Still deliberately not a full language: the gate's job is to catch a
# *contradiction*, so a token it does not know contributes nothing and the pin
# is left alone.
_ESPN_PIN_COUNTRY_WORDS = espn_country_pin_words()

# Code prefixes that name a confederation or a competition family rather than a
# country, so they carry no country evidence.
_ESPN_NON_COUNTRY_PREFIXES = frozenset({
    "uefa", "fifa", "conmebol", "concacaf", "afc", "caf", "club", "global",
    "friendly", "nonfifa", "campeones",
})

_ESPN_PIN_WOMEN_WORDS = frozenset({
    "women", "womens", "woman", "w", "frauen", "feminine", "feminin",
    "femenina", "feminina", "femminile", "vrouwen", "damer", "ladies",
})


# Division markers, read as a tier *rank* so that a digit and a letter naming
# the same tier compare equal.
#
# The digits were the whole check, and that is bug-shaped rather than
# incomplete-shaped: measured against the 2026-08-28 table, "Bundesliga 2 -
# Germany" mispinned to ger.1 was CAUGHT, while "Brasileirao Serie B" -> bra.1,
# "Serie B - Italy" -> ita.1 and "Primera B Nacional" -> arg.1 were all MISSED,
# purely because one names its tier with a digit and the others with a letter.
# Those are the expensive misses: right country, real clubs, nothing raises,
# and the phantom second provider goes on to feed cross_provider_agreement,
# which is what promotes a row from LEAN to CALL.
#
# A letter only counts when the word before it names a league family. A bare
# letter loose in a name means nothing -- "A-League" is aus.1, and a feed
# spelling "UEFA Nations League - League B" names a seeding pot, not a tier --
# so "league" is not a family word and neither is nothing at all.
_ESPN_TIER_FAMILY_WORDS = frozenset({
    "serie", "seria", "primera", "primeira", "segunda", "liga", "ligue",
    "division", "divisione", "divisao", "divisie", "categoria", "nacional",
    "klasse",
})
_ESPN_TIER_LETTERS = {"a": 1, "b": 2, "c": 3, "d": 4}
# Ordinal words that name a tier on their own, in the languages where the word
# is unambiguous. "primera"/"primeira"/"prima" are pointedly absent: Argentina's
# Primera Nacional is the *second* tier, so the word does not carry the rank.
_ESPN_TIER_WORDS = {
    "segunda": 2, "seconda": 2, "zweite": 2, "deuxieme": 2,
    "tercera": 3, "terza": 3, "dritte": 3,
}
# Single digits only: "2025" and "24" are season markers, not tiers. Word
# numbers are deliberately never read -- English "League One" is the *third*
# tier, so "one" does not mean 1 anywhere it appears.
_ESPN_TIER_DIGITS = {"1", "2", "3", "4", "5"}


def _espn_pin_tokens(text: str) -> list[str]:
    """The words of a name, in order. Order matters only for tier letters."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", folded)


def _espn_pin_words(text: str) -> set[str]:
    return set(_espn_pin_tokens(text))


def _espn_division_ranks(tokens: list[str]) -> set[int]:
    """Which tiers this name claims, as ranks. Empty means it claims none."""
    ranks: set[int] = set()
    previous = ""
    for token in tokens:
        if token in _ESPN_TIER_DIGITS:
            ranks.add(int(token))
        elif token in _ESPN_TIER_WORDS:
            ranks.add(_ESPN_TIER_WORDS[token])
        elif token in _ESPN_TIER_LETTERS and previous in _ESPN_TIER_FAMILY_WORDS:
            ranks.add(_ESPN_TIER_LETTERS[token])
        previous = token
    return ranks


# Competition names whose digit is part of a proper noun, mapped to the tier the
# competition actually is. Exact whole-string match only, and the list is
# deliberately tiny.
#
# The general rule above is right and must not be softened: a name carrying "1"
# pinned to a tier-3 code is the exact shape of a paste error, and teaching the
# gate to read "One" as 1 would break the reason the digits rule exists --
# English "League One" *is* the third tier, so the word must never mean 1.
#
# These two are the case where the rule and the truth genuinely diverge. The
# feeds render England's third and fourth tiers as "League 1" and "League 2",
# so the digit is the name and nothing else. Established from the fixtures
# rather than the string, on the 2026-09-01 slate: "League 1" was Bradford
# City, Bromley, Doncaster, Huddersfield, Leicester, Peterborough and Wycombe;
# "League 2" was Accrington, Exeter, Bristol Rovers, Cheltenham, Chesterfield,
# Northampton, Crewe, Fleetwood, Salford, Swindon, Rochdale and Tranmere.
#
# Mapped rather than merely exempted, so the tier check keeps working instead of
# being switched off for these two names. Blanking the rank would let a 3-for-4
# paste error through -- "League 1" pinned to eng.4 -- which is the very class of
# typo this gate exists to catch. Translating it means "League 1" agrees with
# eng.3 and still contradicts eng.4.
#
# Adding to this list means proving the same way: name the fixtures. It is not
# a place to put a name that merely looks awkward.
_ESPN_NAME_DIGIT_TIERS = {"League 1": 3, "League 2": 4}


def _espn_pin_contradicted(competition: str, league: str, league_name: str) -> str:
    """Why ESPN's own league name disagrees with the competition, or "".

    Defence in depth behind the competition table, not a substitute for it.
    The table is exact-match and cannot guess, but a *typo* in it -- one code
    pasted onto the wrong row -- produces exactly the failure that never
    raises: a women's or second-division pin inside the right country answers
    with a real team and a real season, so no data_gap is ever raised and the
    phantom provider feeds cross_provider_agreement. Comparing the competition
    name against the name ESPN files the code under is the only check that
    sees that.

    Only contradictions reject. An unrecognised word proves nothing and is
    ignored, so this gate can never be the reason a correct pin is dropped.
    """
    if not league_name:
        return ""
    comp_tokens = _espn_pin_tokens(competition)
    espn_tokens = _espn_pin_tokens(league_name)
    comp_words = set(comp_tokens)
    espn_words = set(espn_tokens)

    comp_countries = {
        _ESPN_PIN_COUNTRY_WORDS[w] for w in comp_words if w in _ESPN_PIN_COUNTRY_WORDS
    }
    espn_countries = {
        _ESPN_PIN_COUNTRY_WORDS[w] for w in espn_words if w in _ESPN_PIN_COUNTRY_WORDS
    }
    # The code's own prefix is evidence too: ESPN names "ksa.1" the "Saudi Pro
    # League", but names "rsa.1" the "South African Premiership", and only the
    # code says which country a bare name belongs to.
    code_country = league.split(".")[0]
    if code_country.isalpha() and code_country not in _ESPN_NON_COUNTRY_PREFIXES:
        espn_countries.add(code_country)
    if comp_countries and espn_countries and not (comp_countries & espn_countries):
        return (
            f"competition names {sorted(comp_countries)} but ESPN files "
            f"'{league}' as '{league_name}'"
        )

    # One-directional, and this is the limit of the check rather than an
    # oversight: a competition that says "women" pinned to a men's league is the
    # measured failure ("Frauen-Bundesliga" -> ger.1), and it is catchable. The
    # reverse -- a men's competition pinned to a women's league -- is not, because
    # a correct women's pin routinely has no gender word to compare: "WSL" and
    # "NWSL" are the real feed names for eng.w.1 and usa.nwsl. Rejecting on the
    # absence of a word would drop those two correct pins to catch a hypothetical
    # one, and this gate must never be the reason a correct pin is dropped.
    comp_women = bool(comp_words & _ESPN_PIN_WOMEN_WORDS)
    espn_women = bool(espn_words & _ESPN_PIN_WOMEN_WORDS) or ".w." in f".{league}."
    if comp_women and not espn_women:
        return (
            f"competition is women's but ESPN files '{league}' as '{league_name}'"
        )

    named_tier = _ESPN_NAME_DIGIT_TIERS.get(competition.strip())
    comp_div = (
        {named_tier} if named_tier is not None
        else _espn_division_ranks(comp_tokens)
    )
    espn_div = _espn_division_ranks(espn_tokens)
    # The code's tail is the third witness, and the only one that reads "1":
    # ESPN's name for a top flight rarely says which tier it is ("Argentine
    # Liga Profesional"), so without the tail a competition claiming a second
    # tier and a code pinned at a first tier had nothing to disagree about.
    code_div = league.rsplit(".", 1)[-1]
    if code_div in _ESPN_TIER_DIGITS:
        espn_div.add(int(code_div))
    if comp_div and espn_div and not (comp_div & espn_div):
        return (
            f"competition names division {sorted(comp_div)} but ESPN files "
            f"'{league}' as '{league_name}'"
        )
    # Only a claim of a *lower* tier survives a code that names no tier at all.
    # A cup code carries no rank in its tail, and "names division [1] but ESPN
    # files it as a cup" is not a contradiction worth dropping a pin over.
    if comp_div and not espn_div and max(comp_div) > 1:
        return (
            f"competition names division {sorted(comp_div)} but ESPN files "
            f"'{league}' as top-flight '{league_name}'"
        )
    return ""


def espn_competition_coverage(events: Iterable[Any]) -> dict[str, Any]:
    """How much of a slate the ESPN competition table can name, and what it cannot.

    The table is exact-match by design: an unenumerated feed spelling is a lost
    provider rather than a wrong pin, which is the trade this whole module
    makes on purpose. The cost of that trade is measurable on the day it is
    paid and invisible afterwards -- coverage was measured once, on the
    2026-08-28 slate, and nothing in a later run said whether it had held.

    So the run says it. Fixture-weighted as well as name-weighted, because the
    two disagree in exactly the case that matters: on 2026-08-28 "National
    League" was one unresolved *name* and eleven unresolved *fixtures*, the
    largest block in the slate.

    Pure, and free: no network, no provider quota. Football only -- tennis
    resolves through a tour marker, not a league table.
    """
    total = 0
    resolved = 0
    unresolved: dict[str, int] = {}
    for event in events:
        if getattr(event, "sport", None) != "football":
            continue
        competition = str(getattr(event, "competition", "") or "")
        total += 1
        if competition and get_espn_league_for_competition(competition):
            resolved += 1
        else:
            unresolved[competition or "(no competition)"] = (
                unresolved.get(competition or "(no competition)", 0) + 1
            )
    names = {str(getattr(e, "competition", "") or "") for e in events
             if getattr(e, "sport", None) == "football"}
    return {
        "football_fixtures": total,
        "fixtures_resolved": resolved,
        "fixtures_unresolved_pct": (
            round(100.0 * (total - resolved) / total, 1) if total else 0.0
        ),
        "competition_names": len(names),
        "names_unresolved": len(unresolved),
        # Named, not counted: every entry here is one authored table row away
        # from being a second provider, and the name is the whole fix.
        "unresolved_by_fixtures": dict(
            sorted(unresolved.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
    }


def _espn_league_directory(
    sport: str, league: str, rate_limiter: RateLimiter
) -> _ESPNDirectory:
    """Ask ESPN what it serves for this league code, once per process.

    ESPN serves a team directory for its headline leagues and returns HTTP 404
    for the rest: verified live on 2026-08-25, ``esp.1`` returns 20 teams while
    ``sau.1`` and ``kor.1`` both 404, and ``/scoreboard`` answers 400 for them
    with and without a ``dates`` parameter. ``resolve_team_id`` swallows that
    404 and returns None, so the whole failure previously surfaced as "could
    not resolve team identity for 'Abha Club'" -- indistinguishable from a
    genuine name mismatch, and the reason every row of the 2026-08-25 sheet
    came back SINGLE_SOURCE off sportdb alone while ESPN sat on 10000 unspent
    requests.
    """
    with _ESPN_TEAM_DIRECTORY_LOCK:
        cached = _ESPN_TEAM_DIRECTORY.get(league)
    if cached is not None:
        return cached

    from bet.api_clients.espn import ESPNClient

    try:
        probe = ESPNClient(sport=sport, league=league, rate_limiter=rate_limiter)
        payload = probe._request("/teams")
        teams: list[Any] = []
        name = ""
        for sport_block in (payload or {}).get("sports", []):
            for league_block in sport_block.get("leagues", []):
                name = name or str(league_block.get("name") or "")
                teams.extend(league_block.get("teams") or [])
        result = _ESPNDirectory(served=True, league_name=name, team_count=len(teams))
    except Exception:  # noqa: BLE001 - a 404 and a transport error are both "no directory"
        result = _ESPNDirectory(served=False)

    with _ESPN_TEAM_DIRECTORY_LOCK:
        _ESPN_TEAM_DIRECTORY[league] = result
    return result


def _espn_league_has_team_directory(
    sport: str, league: str, rate_limiter: RateLimiter
) -> bool:
    """Whether ESPN answers ``/teams`` for this league with actual teams.

    Kept as the boolean face of _espn_league_directory for preflight, which
    only needs to know whether the league is worth counting.
    """
    return _espn_league_directory(sport, league, rate_limiter).usable


def _provider_client(provider_key: str, competition: str, rate_limiter: RateLimiter) -> Any:
    """Build the client for a provider, scoped to the event's competition.

    get_client("espn-football") pins the league to ``eng.1``
    (api_clients/__init__.py), so every non-English fixture failed at
    resolve_team_id -- ESPN's team search only covers the league its base_url
    points at. ESPN already ships a competition-name -> league-code map, so
    reuse it and build a correctly scoped client instead.

    Scoping alone was not enough: the map answers for most competitions, but
    ESPN then 404s ``/teams`` for the smaller ones. Both failure modes now
    raise ProviderLeagueUnsupported rather than silently falling back to the
    ``eng.1`` client.

    This strictness is football-only on purpose. ``espn-tennis`` resolves a
    player through ESPN's global search API (_resolve_athlete_id), which is not
    league-scoped, so its default client is already correct and refusing to
    build one would break the only sport that currently corroborates.
    """
    if provider_key == "espn-football":
        from bet.api_clients.espn import (
            ESPN_FOOTBALL_LEAGUE_CODES,
            ESPNClient,
            get_espn_league_for_competition,
        )

        if not competition:
            raise ProviderLeagueUnsupported(
                "event carries no competition, cannot scope an ESPN league"
            )
        league = get_espn_league_for_competition(competition)
        if not league:
            raise ProviderLeagueUnsupported(
                f"no ESPN league code for competition '{competition}'"
            )
        # The competition table serves every sport, so a football request must
        # refuse a code that is not a football code. Without this, one mistyped
        # table row pins an ESPNClient(sport="football") to "atp" and the
        # failure surfaces as an unresolvable team name.
        if league not in ESPN_FOOTBALL_LEAGUE_CODES:
            raise ProviderLeagueUnsupported(
                f"'{league}' ('{competition}') is not an ESPN football league code"
            )
        directory = _espn_league_directory("football", league, rate_limiter)
        if not directory.usable:
            raise ProviderLeagueUnsupported(
                f"ESPN publishes no team directory for league "
                f"'{league}' ('{competition}'), so no history can be fetched"
            )
        contradiction = _espn_pin_contradicted(
            competition, league, directory.league_name
        )
        if contradiction:
            raise ProviderLeagueUnsupported(
                f"ESPN league pin for '{competition}' is not trustworthy: "
                f"{contradiction}"
            )
        return ESPNClient(sport="football", league=league, rate_limiter=rate_limiter)
    if provider_key == "espn-tennis":
        from bet.api_clients.espn import ESPNClient, get_espn_league_for_competition

        # ESPN's tennis endpoints are tour-scoped, so an ATP-pinned client
        # scanning for a WTA player gets a real scoreboard that simply never
        # contains her. Only "atp"/"wta" may be pinned here; a football code
        # arriving from the shared table is a table bug, not a tennis league.
        league = get_espn_league_for_competition(competition) if competition else None
        if league in {"atp", "wta"}:
            return ESPNClient(sport="tennis", league=league, rate_limiter=rate_limiter)
        # Nothing else may be pinned. get_espn_league_for_competition's contract
        # says None means "ESPN cannot cover this competition", never "try the
        # default league" -- and this branch used to do exactly the forbidden
        # thing, handing back the registry client, which is pinned to "atp".
        # Every US Open women's fixture on 2026-08-28 therefore asked an
        # ATP-scoped client for a WTA player and was answered by the scoreboard
        # fallback with a man: Qinwen Zheng's L10 came back as Musetti, Humbert,
        # Marozsan, Nishikori. Refusing costs espn-tennis on unlabelled draws
        # (challengers, mostly). That is the cheaper error by a wide margin.
        raise ProviderLeagueUnsupported(
            f"no ESPN tennis tour for competition '{competition}': refusing to "
            f"fall back to the default tour, which serves the wrong player"
        )
    return get_client(provider_key, rate_limiter=rate_limiter)


# Identity is asked once per (provider, player, competition) per process. Both
# callers -- preflight's capability cap and the verification script -- ask the
# same question about the same handful of names, and for tennis-abstract the
# answer costs a page fetch.
_TENNIS_IDENTITY_MEMO: dict[tuple[str, str, str], str | None] = {}
_TENNIS_IDENTITY_LOCK = threading.Lock()


def resolve_tennis_player(
    provider: str, player_name: str, competition: str, rate_limiter: RateLimiter
) -> str | None:
    """The provider's own identifier for this player, or None if it has no such player.

    Resolution is the step that decides whether a tennis provider contributes
    anything, and until 2026-08-28 it was the step that could not fail:
    tennis-abstract's resolve_team_id handed the caller's own string back, so
    every player "resolved" -- including players the site had never heard of,
    and including every WTA player, whose page request the site answers with
    Benoit Paire's. Now both tennis providers answer with a name or an id they
    have actually proved, which is what makes a capability count meaningful and
    what lets a verification script check identity against the provider's own
    name field instead of a similarity score.
    """
    if not player_name:
        return None
    key = (provider, player_name, competition)
    with _TENNIS_IDENTITY_LOCK:
        if key in _TENNIS_IDENTITY_MEMO:
            return _TENNIS_IDENTITY_MEMO[key]
    try:
        client = _provider_client(provider, competition, rate_limiter)
        resolved = client.resolve_team_id(player_name)
    except Exception as exc:  # noqa: BLE001 - an unresolvable player is a gap
        logger.debug("[%s] could not resolve '%s': %s", provider, player_name, exc)
        resolved = None
    with _TENNIS_IDENTITY_LOCK:
        _TENNIS_IDENTITY_MEMO[key] = resolved
    return resolved


@dataclass
class TennisIdentityEvidence:
    """What one tennis provider could actually prove about one player.

    Deliberately not a score. Each field is something the provider stated:
    the id or name it resolved to, the name *it* attached to the rows it
    returned, how many rows there were and how recent the newest one is.
    """

    provider: str
    requested: str
    resolved: str | None = None
    # The provider's own name field for the matches it returned -- tennis
    # abstract's ``var fullname``, ESPN's scoreboard ``displayName`` for the
    # competitor carrying the resolved athlete id. This is the field identity
    # is judged against, because it is the provider's claim rather than ours.
    provider_name: str | None = None
    match_count: int = 0
    newest_match: str = ""
    verdict: str = "UNRESOLVED"
    detail: str = ""


def probe_tennis_identity(
    provider: str,
    player_name: str,
    competition: str,
    rate_limiter: RateLimiter,
    last_n: int = 10,
) -> TennisIdentityEvidence:
    """Ask a tennis provider to prove it can serve *this* player's matches.

    Verdicts, each one a failure the tennis roster has actually shipped:

      PROVED         resolved, returned matches, and every row it returned is
                     named for the player we asked about.
      UNRESOLVED     the provider has nobody by that name. Normal and useful:
                     it is what a capability cap counts.
      MISIDENTIFIED  the provider returned matches belonging to someone else.
                     This is the one that matters. It is not hypothetical:
                     before 2026-08-28 every WTA request to tennis-abstract
                     came back with Benoit Paire's page, at HTTP 200, with a
                     real match table, and the pipeline filed his serve line
                     under her name.
      NO_MATCHES     resolves but has no history to give -- the shape ESPN was
                     in for most ATP players while its scan sampled every third
                     day and landed either side of all of them.

    Reusing the production client and the production resolve/fetch path is the
    point, exactly as verify_espn_competition_map.py runs the runtime pin gate:
    a check that re-implements what it is checking proves only itself.
    """
    from bet.api_clients.tennis_abstract import identity_matches

    evidence = TennisIdentityEvidence(provider=provider, requested=player_name)
    try:
        client = _provider_client(provider, competition, rate_limiter)
    except Exception as exc:  # noqa: BLE001
        evidence.detail = f"client unavailable: {exc}"
        return evidence

    resolved = resolve_tennis_player(provider, player_name, competition, rate_limiter)
    if not resolved:
        evidence.detail = "provider has no player by that name"
        return evidence
    evidence.resolved = str(resolved)

    method_name, unwrap = _LAST_FIXTURES_METHOD.get(provider, _DEFAULT_LAST_FIXTURES_METHOD)
    try:
        raw = getattr(client, method_name)(resolved, last_n=last_n)
        if unwrap:
            raw = raw.value if raw.status == SourceResultStatus.SUCCESS else []
        fixtures = list(raw or [])
    except Exception as exc:  # noqa: BLE001
        evidence.verdict = "NO_MATCHES"
        evidence.detail = f"last-fixtures error: {exc}"
        return evidence

    if not fixtures:
        evidence.verdict = "NO_MATCHES"
        evidence.detail = "resolved, but the provider returned no finished matches"
        return evidence

    # Whose matches are these, according to the provider? For every row, take
    # the side that is *not* the opponent and read the name the provider put
    # on it. A row that cannot say which side the player was on is counted
    # rather than excused: unattributable rows are how a wrong opponent used
    # to get in.
    self_names: list[str] = []
    unattributable = 0
    dates: list[str] = []
    for fixture in fixtures:
        dates.append(str(_field(fixture, "date", "kickoff", default="") or "")[:10])
        opponent = _opponent_of(fixture, str(resolved))
        if opponent is None:
            unattributable += 1
            continue
        home = _field(fixture, "home_team", default="")
        away = _field(fixture, "away_team", default="")
        self_names.append(str(away if str(home) == str(opponent) else home))

    evidence.match_count = len(fixtures)
    evidence.newest_match = max((d for d in dates if d), default="")
    stated = next((n for n in self_names if n), None)
    evidence.provider_name = stated or (str(resolved) if provider == "tennis-abstract" else None)

    if unattributable:
        evidence.verdict = "MISIDENTIFIED"
        evidence.detail = (
            f"{unattributable} of {len(fixtures)} rows do not say which side "
            f"the player was on"
        )
        return evidence

    wrong = sorted({n for n in self_names if n and not identity_matches(player_name, n)})
    if wrong:
        evidence.verdict = "MISIDENTIFIED"
        evidence.detail = f"provider named the player {', '.join(repr(n) for n in wrong)}"
        return evidence

    evidence.verdict = "PROVED"
    evidence.detail = f"{len(fixtures)} matches, newest {evidence.newest_match or 'unknown'}"
    return evidence


# Providers whose rows are one *person's*, so a row naming somebody else is a
# crossing rather than a data gap. Football is excluded: a club's fixture rows
# name two clubs and the l10 loop already proves which side by team id.
_NAME_ADDRESSED_TENNIS_PROVIDERS = frozenset({"tennis-abstract", "espn-tennis", "sackmann"})


def _misidentified_reason(
    provider_key: str, requested_name: str, resolved_id: str, fixtures: list
) -> str | None:
    """Whose matches are these, according to the provider? None if they are his.

    This is ``probe_tennis_identity``'s check, moved onto the path that actually
    builds the stats sheet. Until now the proof existed only in
    ``verify_tennis_providers.py``, which probes a fixed list of canary names
    before a run -- so a crossing on one of the day's *actual* players passed
    the morning check untouched and reached the coupon looking measured. That is
    what happened on 2026-08-28: the script exited 0 and Qinwen Zheng's sheet
    carried Lorenzo Musetti's matches.

    Costs no extra call: the rows are already in hand, and every one of them
    states the two names. A row that cannot say which side the player was on is
    a failure, not an abstention -- an unattributable row is how a wrong
    opponent got in before.
    """
    if provider_key not in _NAME_ADDRESSED_TENNIS_PROVIDERS or not requested_name:
        return None
    from bet.api_clients.tennis_abstract import identity_matches

    wrong: set[str] = set()
    unattributable = 0
    for fixture in fixtures:
        opponent = _opponent_of(fixture, str(resolved_id))
        if opponent is None:
            unattributable += 1
            continue
        home = _field(fixture, "home_team", default="")
        away = _field(fixture, "away_team", default="")
        stated = str(away if str(home) == str(opponent) else home)
        if stated and not identity_matches(requested_name, stated):
            wrong.add(stated)
    if unattributable:
        return (
            f"{unattributable} of {len(fixtures)} rows do not say which side "
            f"'{requested_name}' played"
        )
    if wrong:
        return (
            f"rows belong to {', '.join(repr(n) for n in sorted(wrong))}, "
            f"not to '{requested_name}'"
        )
    return None


def _fetch_l10_generic(
    provider_key: str, team_name: str, rate_limiter: RateLimiter, last_n: int = 10, competition: str = ""
) -> FetchOutcome:
    outcome = FetchOutcome()
    aliases = _ALIASES_BY_PROVIDER[provider_key]
    method_name, unwrap = _LAST_FIXTURES_METHOD.get(provider_key, _DEFAULT_LAST_FIXTURES_METHOD)
    try:
        client = _provider_client(provider_key, competition, rate_limiter)
        team_id = client.resolve_team_id(team_name)
    except Exception as exc:  # noqa: BLE001 - any provider failure is a data_gap, never a crash
        outcome.data_gaps.append(f"{provider_key}: {exc}")
        return outcome
    if not team_id:
        # Named the way it is because the alternative was measured and was
        # worse. On 2026-09-02 api-football's account was suspended; it answers
        # that with HTTP 200, an empty ``response`` and one sentence in
        # ``errors.access``, so every lookup came back None and this line fired
        # 472 times against Flamengo, Celtic, Udinese, AGF, Motherwell and West
        # Brom. Read off the artifact that is a missing-alias problem, and it
        # is not: the provider contributed zero observations all day. The
        # entitlement fault now raises out of ``resolve_team_id`` into the
        # handler above, so this branch is once again what it claims to be --
        # a provider that answered, and does not know this club.
        outcome.data_gaps.append(f"{provider_key}: could not resolve team identity for '{team_name}'")
        return outcome
    try:
        raw = getattr(client, method_name)(
            team_id, last_n=last_n,
            **_draw_filter_kwargs(provider_key, competition),
        )
        if unwrap:
            if raw.status != SourceResultStatus.SUCCESS:
                outcome.data_gaps.append(f"{provider_key}: {raw.status.value} fetching last fixtures")
                return outcome
            fixtures = raw.value or []
        else:
            fixtures = raw or []
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"{provider_key}: last-fixtures error for '{team_name}': {exc}")
        return outcome
    if not fixtures:
        outcome.data_gaps.append(f"{provider_key}: no recent matches for '{team_name}'")
        return outcome
    crossed = _misidentified_reason(provider_key, team_name, str(team_id), fixtures)
    if crossed:
        # The whole payload is dropped, not the offending rows. A provider that
        # served one wrong player's match has not proved which of the others are
        # right, and a half-believed L10 is the shape the Benoit Paire
        # fabrication took: real numbers, real table, wrong human.
        outcome.data_gaps.append(f"{provider_key}: MISIDENTIFIED for '{team_name}': {crossed}")
        return outcome
    for fx in fixtures:
        fixture_id = _field(fx, "id", "fixture_id")
        if not fixture_id:
            continue
        try:
            raw_stats = client.get_fixture_stats(fixture_id)
        except Exception as exc:  # noqa: BLE001
            outcome.data_gaps.append(f"{provider_key}: fixture {fixture_id} stats error: {exc}")
            continue
        if isinstance(raw_stats, list):
            raw_stats = raw_stats[0] if raw_stats else None
        if raw_stats is None:
            continue
        stats_dict = getattr(raw_stats, "stats", None) or {}
        opponent = _opponent_of(fx, team_id)
        if opponent is None:
            outcome.data_gaps.append(
                f"{provider_key}: fixture {fixture_id} does not identify which "
                f"side '{team_name}' played; refusing to guess an opponent"
            )
            continue
        combined = _combine_stats(provider_key, stats_dict, aliases)
        if _tennis_match_unfinished(provider_key, stats_dict):
            outcome.data_gaps.append(
                f"{provider_key}: fixture {fixture_id} did not finish "
                f"(score '{stats_dict.get('score', '')}'); recorded as absent"
            )
            continue
        if _is_absent_not_zero(combined, provider_key):
            outcome.data_gaps.append(
                f"{provider_key}: fixture {fixture_id} is not a completed match "
                f"(retirement, walkover, or every stat 0); recorded as absent"
            )
            continue
        # Added *after* the absent-payload check above, never before: a real
        # 0-0 draw's goals are a correct observation, but merging them into
        # `combined` earlier would let a goals row rescue a payload that
        # should have been rejected as absent (a-zero-that-means-unknown).
        # espn-football is the only provider in this generic path whose
        # fixture row carries a final score at all -- api-football's does
        # not, and the two tennis providers' "score" means games/sets, not
        # goals.
        # Hoisted out of the espn-football branch below, which is where this
        # lookup used to live: which side the team played on is what splits
        # that match's goals *and* what ``ProviderValue.venue`` records, and
        # the second use is not football-score-specific. ``_venue_or_none``
        # discards it for the tennis providers that share this function.
        side = _side_of(fx, team_id)
        if provider_key == "espn-football":
            home_goals, away_goals = _parse_espn_score(_field(fx, "score"))
            if home_goals is not None and away_goals is not None:
                combined["goals_total"] = home_goals + away_goals
                if side is not None:
                    combined["goals_for"] = home_goals if side == "home" else away_goals
                    combined["goals_against"] = away_goals if side == "home" else home_goals
        for name, value in _make_values(
            provider_key, fixture_id, _field(fx, "date", "kickoff", default=""), str(opponent or "unknown"), combined,
            competition_id=_field(fx, "competition_provider_id", "league_id", "league"),
            season_id=_field(fx, "season", "season_id"),
            side=side,
            # tennis-abstract states the surface on the same stats row the
            # counts come from; espn-tennis names the tournament instead and is
            # resolved through the surface table. ``_surface_or_none`` discards
            # either for the football providers that share this function.
            surface=_row_surface(provider_key, stats_dict, fx),
            # Same two-spellings arrangement as ``surface`` directly above:
            # tennis-abstract states the draw on the stats row, espn-tennis
            # names the tournament. ``_match_level_or_none`` discards either
            # for the football providers that share this function.
            match_level=_row_match_level(provider_key, stats_dict, fx),
        ).items():
            outcome.add(name, value)
    return outcome


def _fetch_h2h_generic(
    provider_key: str, team_one: str, team_two: str, rate_limiter: RateLimiter, last_n: int = 10,
    competition: str = "",
) -> FetchOutcome:
    outcome = FetchOutcome()
    aliases = _ALIASES_BY_PROVIDER[provider_key]
    try:
        client = _provider_client(provider_key, competition, rate_limiter)
        id_one = client.resolve_team_id(team_one)
        id_two = client.resolve_team_id(team_two)
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"{provider_key}: {exc}")
        return outcome
    if not id_one or not id_two:
        outcome.data_gaps.append(f"{provider_key}: could not resolve h2h identity for '{team_one}' vs '{team_two}'")
        return outcome
    try:
        meetings = client.get_h2h(id_one, id_two, last_n=last_n) or []
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"{provider_key}: h2h error for '{team_one}' vs '{team_two}': {exc}")
        return outcome
    if not meetings:
        outcome.data_gaps.append(f"{provider_key}: no h2h meetings for '{team_one}' vs '{team_two}'")
        return outcome
    for meeting in meetings:
        fixture_id = _field(meeting, "id", "fixture_id")
        if not fixture_id:
            continue
        try:
            raw_stats = client.get_fixture_stats(fixture_id)
        except Exception as exc:  # noqa: BLE001
            outcome.data_gaps.append(f"{provider_key}: h2h fixture {fixture_id} stats error: {exc}")
            continue
        if isinstance(raw_stats, list):
            raw_stats = raw_stats[0] if raw_stats else None
        if raw_stats is None:
            continue
        stats_dict = getattr(raw_stats, "stats", None) or {}
        combined = _combine_stats(provider_key, stats_dict, aliases)
        if _tennis_match_unfinished(provider_key, stats_dict):
            outcome.data_gaps.append(
                f"{provider_key}: h2h fixture {fixture_id} did not finish "
                f"(score '{stats_dict.get('score', '')}'); recorded as absent"
            )
            continue
        if _is_absent_not_zero(combined, provider_key):
            outcome.data_gaps.append(
                f"{provider_key}: h2h fixture {fixture_id} is not a completed match "
                f"(retirement, walkover, or every stat 0); recorded as absent"
            )
            continue
        # No ``side``, so no venue. An H2H value carries no marker for which
        # of the two teams it belongs to -- which is exactly why
        # ``_team_total_rows`` refuses to read this bucket for a per-team row
        # at all -- and a venue attributed to the wrong side is worse than an
        # absent one.
        for name, value in _make_values(
            provider_key, fixture_id, _field(meeting, "date", "kickoff", default=""), team_two, combined,
            competition_id=_field(meeting, "competition_provider_id", "league_id", "league"),
            season_id=_field(meeting, "season", "season_id"),
            # Surface is a property of the meeting, not of a side, so unlike
            # ``venue`` above it is recorded for h2h too: a past meeting on
            # clay is no more a trial of tonight's hard court than one of
            # either player's own clay matches would be.
            surface=_row_surface(provider_key, stats_dict, meeting),
            # And the draw is a property of the meeting for the same reason:
            # a past meeting in a best-of-three tour event says nothing about
            # how long tonight's best-of-five tie runs, whichever side it was.
            match_level=_row_match_level(provider_key, stats_dict, meeting),
        ).items():
            outcome.add(name, value)
    return outcome


def fetch_provider_team_metrics(
    provider: str, team_name: str, competition: str, rate_limiter: RateLimiter
) -> FetchOutcome:
    """Single-(event, provider) L10 fetch, for ENRICH's per-provider concurrency unit."""
    if provider == "understat":
        return fetch_understat_l10(team_name, competition, rate_limiter)
    return _fetch_l10_generic(provider, team_name, rate_limiter, competition=competition)


def fetch_provider_h2h_metrics(
    provider: str, team_one: str, team_two: str, rate_limiter: RateLimiter, competition: str = ""
) -> FetchOutcome:
    """Single-(event, provider) H2H fetch, for ENRICH's per-provider concurrency unit."""
    if provider not in _H2H_SUPPORTED_PROVIDERS:
        return FetchOutcome(data_gaps=[f"{provider}: h2h fetch not supported"])
    return _fetch_h2h_generic(provider, team_one, team_two, rate_limiter, competition=competition)


def fetch_understat_l10(team_name: str, competition: str, rate_limiter: RateLimiter) -> FetchOutcome:
    outcome = FetchOutcome()
    try:
        client = get_client("understat", rate_limiter=rate_limiter)
        matches = client.get_team_matches(team_name, competition) or []
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"understat: {exc}")
        return outcome
    if not matches:
        outcome.data_gaps.append(f"understat: no matches for '{team_name}' in '{competition}'")
        return outcome
    for m in matches:
        stats_dict = getattr(m, "stats", None) or {}
        combined = _combined_from_dict_stats(stats_dict, _UNDERSTAT_ALIASES)
        home_team = getattr(m, "home_team", "") or ""
        away_team = getattr(m, "away_team", "") or ""
        opponent = away_team if home_team == team_name else home_team
        # Name-matched rather than id-matched, because understat's rows carry
        # names only. A row naming neither side leaves the venue unstated
        # instead of defaulting to away.
        if home_team and home_team == team_name:
            side = "home"
        elif away_team and away_team == team_name:
            side = "away"
        else:
            side = None
        for name, value in _make_values(
            "understat", getattr(m, "fixture_id", ""), getattr(m, "date", ""), opponent, combined,
            side=side,
        ).items():
            outcome.add(name, value)
    return outcome


def fetch_team_metrics(sport: str, team_name: str, competition: str, rate_limiter: RateLimiter) -> FetchOutcome:
    """Fetch L10 metric observations for one team/player from every applicable
    provider for this sport, combining (not falling back) across providers."""
    combined = FetchOutcome()
    for provider in PROVIDERS_BY_SPORT[sport]:
        if provider == "understat":
            combined.merge(fetch_understat_l10(team_name, competition, rate_limiter))
        else:
            combined.merge(_fetch_l10_generic(provider, team_name, rate_limiter, competition=competition))
    return combined


def fetch_h2h_metrics(
    sport: str, team_one: str, team_two: str, rate_limiter: RateLimiter, competition: str = ""
) -> FetchOutcome:
    """Fetch head-to-head metric observations between two teams/players,
    combining across every provider that supports name-based H2H lookup.

    ``competition`` is what scopes the provider client -- an espn-football H2H
    without it cannot be built at all, and an espn-tennis one silently searches
    the wrong tour. It was accepted by the per-provider entry point
    (fetch_provider_h2h_metrics) and by _fetch_h2h_generic, but this function
    dropped it on the floor, so every caller that came through here asked for
    H2H with no competition and got the default-scoped client.
    """
    combined = FetchOutcome()
    for provider in PROVIDERS_BY_SPORT[sport]:
        if provider not in _H2H_SUPPORTED_PROVIDERS:
            combined.data_gaps.append(f"{provider}: h2h fetch not supported")
            continue
        combined.merge(
            _fetch_h2h_generic(
                provider, team_one, team_two, rate_limiter, competition=competition
            )
        )
    return combined


_HIGHLIGHTLY_STATS_CACHE: dict[str, tuple[dict[str, float], str | None]] = {}
_HIGHLIGHTLY_STATS_LOCK = threading.Lock()


def _highlightly_match_totals(
    client: Any, match_id: str, home_team_id: str, away_team_id: str
) -> tuple[dict[str, float], str | None]:
    """Combined (home+away) canonical totals for one Highlightly match.

    ``get_statistics_result`` is not merely guarded by home_team_id/away_team_id
    -- it matches them against each payload row's ``team.id`` to decide the
    row's side, and returns a SCHEMA_ERROR ("unexpected_team_id") when neither
    matches (api_clients/highlightly.py:601-607). Passing this provider's real
    native team ids is therefore mandatory, which is why discovery records them
    on EventRecord.provider_team_ids.
    """
    # The same historical match shows up in both teams' L10 and again in their
    # H2H, and Highlightly's plan quota is the binding constraint on this
    # provider, so each match's stats are fetched at most once per process.
    with _HIGHLIGHTLY_STATS_LOCK:
        cached = _HIGHLIGHTLY_STATS_CACHE.get(match_id)
    if cached is not None:
        return cached

    result = client.get_statistics_result(
        match_id, home_team_id=home_team_id, away_team_id=away_team_id
    )
    if result.status != SourceResultStatus.SUCCESS or not result.value:
        status_label = getattr(result.status, "value", str(result.status))
        gap = f"highlightly: {status_label} for match {match_id}"
        with _HIGHLIGHTLY_STATS_LOCK:
            _HIGHLIGHTLY_STATS_CACHE[match_id] = ({}, gap)
        return {}, gap

    combined: dict[str, float] = {}
    for row in result.value.get("statistics", []):
        canonical = _HIGHLIGHTLY_NORMALIZED_ALIASES.get(row.get("normalized_metric_name") or "")
        if canonical is None:
            continue
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        combined[canonical] = combined.get(canonical, 0.0) + value

    # Highlightly reports shots split into on-target/off-target/blocked rather
    # than as one "total shots" row, but shots_total is one of football's three
    # priority metrics (contracts.PRIORITY_METRICS), so deriving it here is what
    # lets Highlightly corroborate ESPN/SportDB on it instead of silently
    # missing the metric.
    parts = [
        combined.get(k)
        for k in ("shots_on_target_total", "shots_off_target_total", "blocked_shots_total")
    ]
    if any(p is not None for p in parts):
        combined["shots_total"] = sum(p for p in parts if p is not None)

    # Possession arrives as a 0..1 ratio here but as 0..100 points from ESPN /
    # SportDB; rescale so cross_provider_agreement compares like with like.
    if "possession" in combined and combined["possession"] <= 1.5:
        combined["possession"] *= 100.0

    with _HIGHLIGHTLY_STATS_LOCK:
        _HIGHLIGHTLY_STATS_CACHE[match_id] = (combined, None)
    return combined, None


def fetch_highlightly_history(
    team_id: str,
    opposite_team_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
    last_n: int = 10,
    mode: str = "l10",
) -> FetchOutcome:
    """Historical per-match canonical totals from Highlightly for one side
    (``mode="l10"``) or for the two sides' head-to-head (``mode="h2h"``).

    Both listing endpoints hand back each historical match's id *and* both of
    its native team ids, which is exactly what /statistics needs -- so unlike
    the L10-by-team-name path used for ESPN/api-football, no team-name
    resolver is required.
    """
    outcome = FetchOutcome()
    if not team_id or (mode == "h2h" and not opposite_team_id):
        outcome.data_gaps.append(f"highlightly: missing native team id for {mode}")
        return outcome
    if run_budget is not None and not run_budget.try_consume("highlightly"):
        outcome.data_gaps.append("highlightly: run budget exhausted")
        return outcome

    try:
        client = get_client("highlightly", rate_limiter=rate_limiter)
        if mode == "h2h":
            listing = client.get_head_to_head_result(team_id, opposite_team_id)
        else:
            listing = client.get_last_five_games_result(team_id, requested_sample_size=last_n)
    except Exception as exc:  # noqa: BLE001 - any provider failure is a data_gap, never a crash
        outcome.data_gaps.append(f"highlightly: {mode} error: {exc}")
        return outcome

    if listing.status != SourceResultStatus.SUCCESS or not listing.value:
        status_label = getattr(listing.status, "value", str(listing.status))
        outcome.data_gaps.append(f"highlightly: {status_label} listing {mode} for team {team_id}")
        return outcome

    matches = listing.value.get("matches") or []
    if not matches:
        outcome.data_gaps.append(f"highlightly: no {mode} matches for team {team_id}")
        return outcome

    for match in matches[:last_n]:
        match_id = str(match.get("provider_match_id") or "")
        if not match_id:
            continue
        # /last-five-games nests ids under home_team/away_team; /head-2-head
        # returns them flat. Accept both rather than branching on mode.
        home_block = match.get("home_team")
        away_block = match.get("away_team")
        if isinstance(home_block, dict):
            home_id = str(home_block.get("provider_team_id") or "")
            home_name = str(home_block.get("team_name") or "")
        else:
            home_id = str(match.get("home_team_id") or "")
            home_name = str(match.get("home_team_name") or "")
        if isinstance(away_block, dict):
            away_id = str(away_block.get("provider_team_id") or "")
            away_name = str(away_block.get("team_name") or "")
        else:
            away_id = str(match.get("away_team_id") or "")
            away_name = str(match.get("away_team_name") or "")
        if not home_id or not away_id or home_id == away_id:
            continue
        # An event that has not been played yet has no /statistics payload --
        # the client answers SCHEMA_ERROR "statistics_empty". Skipping it here
        # keeps that expected, uninformative outcome out of data_gaps, which
        # exists to flag real coverage problems.
        status = str(match.get("match_status") or match.get("status") or "").lower()
        if status and status not in ("finished", "ft", "match finished", "aet", "after et", "pen"):
            continue

        opponent = away_name if home_id == str(team_id) else home_name
        match_date = str(match.get("date") or match.get("kickoff") or "")
        # `home_away` is the listing's own answer and only the l10 shape
        # carries it (`_normalize_h2h_row` does not), so an h2h row leaves the
        # venue unstated -- the same rule the goals split below already
        # followed, now named once and reused rather than re-read.
        listed_side = match.get("home_away") if mode != "h2h" else None
        side = listed_side if listed_side in ("home", "away") else None

        # Goals ride on the listing row itself -- `_normalize_match_row` already
        # parses `score` -- so they are emitted before the run-budget check and
        # the /statistics call below, and never depend on either succeeding.
        # `home_away` is only ever set for the l10 shape (`_normalize_h2h_row`
        # does not carry it), so h2h matches fall through to `goals_total` only,
        # the same split bzzoiro's history path applies.
        score = match.get("score") or {}
        home_goals, away_goals = score.get("home"), score.get("away")
        if home_goals is not None and away_goals is not None:
            goal_values = {"goals_total": float(home_goals) + float(away_goals)}
            if side is not None:
                goal_values["goals_for"] = float(home_goals if side == "home" else away_goals)
                goal_values["goals_against"] = float(away_goals if side == "home" else home_goals)
            for name, value in _make_values(
                "highlightly", match_id, match_date, opponent or "unknown", goal_values,
                competition_id=match.get("competition_provider_id"),
                season_id=match.get("season"),
                side=side,
            ).items():
                outcome.add(name, value)

        if run_budget is not None and not run_budget.try_consume("highlightly"):
            outcome.data_gaps.append("highlightly: run budget exhausted mid-history")
            break
        try:
            combined, gap = _highlightly_match_totals(client, match_id, home_id, away_id)
        except Exception as exc:  # noqa: BLE001
            outcome.data_gaps.append(f"highlightly: match {match_id} stats error: {exc}")
            continue
        if gap:
            outcome.data_gaps.append(gap)
            continue

        for name, value in _make_values(
            "highlightly", match_id, match_date, opponent or "unknown", combined,
            competition_id=match.get("competition_provider_id"),
            season_id=match.get("season"),
            side=side,
        ).items():
            outcome.add(name, value)
    return outcome


# --------------------------------------------------------------------- bzzoiro

# How far back a "last ten" may reach. Matches _MAX_OBSERVATION_AGE_DAYS, the
# window _is_recent enforces on the way out: asking the provider for anything
# older would spend a call per match on observations that are then discarded.
_BZZOIRO_HISTORY_WINDOW_DAYS = 500

# event_id -> ({"home": {canonical_for: value}, "away": {...},
#               "total": {canonical_total: value}}, gap)
_BZZOIRO_STATS_CACHE: dict[str, tuple[dict[str, dict[str, float]], str | None]] = {}
_BZZOIRO_STATS_LOCK = threading.Lock()

# (team_id, date_from, date_to, last_n) -> the team's newest finished fixtures.
# Separate from the stats cache because it caches the *listing*, and the listing
# is what the player-prop path needs to put a date and an opponent on a box
# score: /players/{id}/stats/ rows carry neither. Without this cache, collecting
# props would re-pay the one-or-two-call ascending-offset dance that the "_for"
# metrics already paid for the same team, in the same window, in the same run.
_BZZOIRO_FIXTURES_CACHE: dict[tuple[str, str, str, int], list[dict]] = {}
_BZZOIRO_FIXTURES_LOCK = threading.Lock()


def reset_bzzoiro_fixtures_cache() -> None:
    """Forget cached team-fixtures listings. For tests, and for a long-lived
    process that should not serve one betting day's fixtures to the next."""
    with _BZZOIRO_FIXTURES_LOCK:
        _BZZOIRO_FIXTURES_CACHE.clear()

# Sentinel gap meaning "the provider covers this fixture but published no stats
# for it". Counted rather than listed; see _bzzoiro_match_stats.
_BZZOIRO_NO_STATS = "__bzzoiro_no_published_stats__"


def _bzzoiro_match_stats(
    client: Any, event_id: str
) -> tuple[dict[str, dict[str, float]], str | None]:
    """One historical match's stats, per side *and* summed.

    Returns ``({"home": ..., "away": ..., "total": ...}, gap)``. Both readings
    come out of one request because they come out of one payload: this provider
    reports the two sides separately, so the match total is a sum this function
    performs rather than the only figure available.

    Cached per event_id for the same reason Highlightly's is: a league fixture
    the two sides already played appears in team A's last ten, in team B's last
    ten, and again in their H2H, so an uncached fetch pays for it three times.
    """
    with _BZZOIRO_STATS_LOCK:
        cached = _BZZOIRO_STATS_CACHE.get(event_id)
    if cached is not None:
        return cached

    result = client.get_statistics_result(event_id)
    if result.status != SourceResultStatus.SUCCESS or not result.value:
        # "statistics_empty" is coverage, not failure: the provider knows the
        # fixture and published no stats for it. In practice that is pre-season
        # friendlies -- four of Lyon's newest ten on 2026-08-26 -- and reporting
        # each one as its own data_gap buried the real gaps under noise from
        # matches nobody would have used as evidence anyway. The caller counts
        # these and reports one line per team instead.
        gap = (
            _BZZOIRO_NO_STATS
            if result.error_code == "statistics_empty"
            else f"bzzoiro: {getattr(result.status, 'value', result.status)} for event {event_id}"
        )
        with _BZZOIRO_STATS_LOCK:
            _BZZOIRO_STATS_CACHE[event_id] = ({}, gap)
        return {}, gap

    per_side: dict[str, dict[str, float]] = {"home": {}, "away": {}}
    totals: dict[str, float] = {}
    for row in result.value.get("statistics", []):
        normalized = row.get("normalized_metric_name") or ""
        side = row.get("side")
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue

        total_name = _BZZOIRO_TOTAL_ALIASES.get(normalized)
        if total_name is not None:
            totals[total_name] = totals.get(total_name, 0.0) + value
        for_name = _BZZOIRO_FOR_ALIASES.get(normalized)
        if for_name is not None and side in per_side:
            per_side[side][for_name] = per_side[side].get(for_name, 0.0) + value

        for period in _BZZOIRO_HALF_PERIODS:
            half_total_name = _BZZOIRO_TOTAL_ALIASES_BY_PERIOD[period].get(normalized)
            if half_total_name is not None:
                totals[half_total_name] = totals.get(half_total_name, 0.0) + value
            half_for_name = _BZZOIRO_FOR_ALIASES_BY_PERIOD[period].get(normalized)
            if half_for_name is not None and side in per_side:
                per_side[side][half_for_name] = per_side[side].get(half_for_name, 0.0) + value

    stats = {"home": per_side["home"], "away": per_side["away"], "total": totals}
    with _BZZOIRO_STATS_LOCK:
        _BZZOIRO_STATS_CACHE[event_id] = (stats, None)
    return stats, None


def _bzzoiro_window(as_of_date: str) -> tuple[str, str]:
    """(date_from, date_to) for history read as of ``as_of_date`` (YYYY-MM-DD).

    ``date_to`` is the *event's* date, not today's. Both are required by the
    provider: with no ``date_to`` ``/teams/{id}/fixtures/`` returns only upcoming
    fixtures, and with no ``date_from`` it reaches back to rows stamped 1970.

    Anchoring on the event rather than on now is what keeps a backfill honest --
    re-running an old date must not build a "last ten" out of matches played
    after the fixture being priced.
    """
    try:
        anchor = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        anchor = datetime.now(UTC).replace(tzinfo=None)
    start = anchor - timedelta(days=_BZZOIRO_HISTORY_WINDOW_DAYS)
    return start.strftime("%Y-%m-%d"), anchor.strftime("%Y-%m-%d")


def _bzzoiro_recent_fixtures(
    client: Any,
    team_id: str,
    date_from: str,
    date_to: str,
    last_n: int,
    run_budget: RunBudget | None,
    gaps: list[str],
) -> list[dict]:
    """The team's ``last_n`` most recent finished fixtures, newest first.

    This listing pages *ascending* and ignores ``ordering`` (verified live), so
    page one is the team's oldest matches in the window -- for a club with two
    seasons of history, matches from 2024. The newest rows are at the end, which
    is why the total is read first and used as an offset.

    Costs one call when the window holds ``last_n`` or fewer matches, two
    otherwise, and nothing at all on a repeat for the same team and window --
    the H2H and player-prop paths both land here for a team the "_for" path has
    already read.
    """
    cache_key = (str(team_id), date_from, date_to, last_n)
    with _BZZOIRO_FIXTURES_LOCK:
        cached = _BZZOIRO_FIXTURES_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    if run_budget is not None and not run_budget.try_consume("bzzoiro"):
        gaps.append("bzzoiro: run budget exhausted before team history")
        return []
    first = client.get_team_fixtures_result(
        team_id, date_from=date_from, date_to=date_to, limit=last_n
    )
    if first.status not in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
        status_label = getattr(first.status, "value", str(first.status))
        gaps.append(f"bzzoiro: {status_label} listing history for team {team_id}")
        return []

    value = first.value or {}
    total = int(value.get("total_count") or 0)
    matches = list(value.get("matches") or [])
    if total > last_n:
        if run_budget is not None and not run_budget.try_consume("bzzoiro"):
            gaps.append("bzzoiro: run budget exhausted before newest history page")
        else:
            tail = client.get_team_fixtures_result(
                team_id,
                date_from=date_from,
                date_to=date_to,
                limit=last_n,
                offset=max(0, total - last_n),
            )
            if tail.status in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
                matches = list((tail.value or {}).get("matches") or [])
            else:
                status_label = getattr(tail.status, "value", str(tail.status))
                gaps.append(
                    f"bzzoiro: {status_label} paging to newest history for team {team_id}"
                )

    matches.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    newest = matches[:last_n]
    with _BZZOIRO_FIXTURES_LOCK:
        _BZZOIRO_FIXTURES_CACHE[cache_key] = list(newest)
    return newest


def fetch_bzzoiro_history(
    team_id: str,
    opposite_team_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
    last_n: int = 10,
    mode: str = "l10",
    as_of_date: str = "",
    event_id: str = "",
) -> FetchOutcome:
    """Historical canonical metrics from Bzzoiro for one side (``mode="l10"``)
    or for the pair's head-to-head (``mode="h2h"``).

    In ``l10`` mode this emits **two** families per historical match: the
    combined ``*_total`` every other provider also reports, so Bzzoiro
    corroborates them, and the ``*_for`` figures for *this* team's own side,
    which no other provider in the roster can supply.

    In ``h2h`` mode only ``*_total`` is emitted. An H2H sample is a property of
    the meeting, not of one side, and the slot carries no marker for which team
    a "for" value would belong to -- so labelling one side's corners as the
    event's ``corners_for`` would silently mix the two teams' samples in the one
    place where that is impossible to notice.

    H2H costs no listing call: the meeting history is embedded in the fixture
    itself (``/events/{id}/`` -> ``head_to_head.recent_matches``), which is why
    ``event_id`` -- this provider's id for the fixture being priced, from
    ``EventRecord.source_ids["bzzoiro"]`` -- is what that mode needs rather than
    a pair of team ids.
    """
    outcome = FetchOutcome()
    if mode == "h2h":
        if not event_id:
            outcome.data_gaps.append("bzzoiro: missing native event id for h2h")
            return outcome
    elif not team_id:
        outcome.data_gaps.append("bzzoiro: missing native team id for l10")
        return outcome

    date_from, date_to = _bzzoiro_window(as_of_date)
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        if mode == "h2h":
            if run_budget is not None and not run_budget.try_consume("bzzoiro"):
                outcome.data_gaps.append("bzzoiro: run budget exhausted before h2h")
                return outcome
            listing = client.get_event_result(event_id)
            if listing.status not in (
                SourceResultStatus.SUCCESS,
                SourceResultStatus.VALID_EMPTY,
            ):
                status_label = getattr(listing.status, "value", str(listing.status))
                outcome.data_gaps.append(
                    f"bzzoiro: {status_label} reading h2h for event {event_id}"
                )
                return outcome
            matches = list((listing.value or {}).get("matches") or [])[:last_n]
        else:
            matches = _bzzoiro_recent_fixtures(
                client,
                str(team_id),
                date_from,
                date_to,
                last_n,
                run_budget,
                outcome.data_gaps,
            )
    except Exception as exc:  # noqa: BLE001 - any provider failure is a data_gap, never a crash
        outcome.data_gaps.append(f"bzzoiro: {mode} error: {exc}")
        return outcome

    if not matches:
        outcome.data_gaps.append(f"bzzoiro: no {mode} matches for team {team_id}")
        return outcome

    considered = 0
    without_stats = 0
    for match in matches:
        match_id = str(match.get("provider_match_id") or "")
        if not match_id or match_id == str(event_id):
            continue
        status = str(match.get("match_status") or "").lower()
        # A postponed or not-yet-played fixture has no /stats payload; calling
        # for it spends a request to receive an expected SCHEMA_ERROR, and
        # recording that as a data_gap buries the real coverage problems.
        if status and status not in BZZOIRO_FINISHED_STATUSES:
            continue

        home = match.get("home_team") or {}
        away = match.get("away_team") or {}
        home_id = str(home.get("provider_team_id") or "")
        away_id = str(away.get("provider_team_id") or "")
        if not home_id or not away_id:
            continue

        side = None
        if mode != "h2h":
            side = "home" if home_id == str(team_id) else "away" if away_id == str(team_id) else None
        opponent = away.get("team_name") if home_id == str(team_id) else home.get("team_name")
        match_date = str(match.get("date") or match.get("kickoff") or "")

        # Goals ride on the fixture listing itself (`score`, already fetched
        # above with the match), so they are emitted here -- before the budget
        # check and the /stats/ call below -- and never depend on either. A
        # match with a result but no published stats (common in h2h, where
        # roughly 8 of 10 meetings carry no box score) still gives goals a
        # real sample; `n` for goals will therefore run ahead of `n` for
        # corners/cards on the same match, same as sample_size already varies
        # market to market on one dossier.
        score = match.get("score") or {}
        home_goals, away_goals = score.get("home"), score.get("away")
        if home_goals is not None and away_goals is not None:
            goal_values = {"goals_total": float(home_goals) + float(away_goals)}
            if side is not None:
                goal_values["goals_for"] = float(home_goals if side == "home" else away_goals)
                goal_values["goals_against"] = float(away_goals if side == "home" else home_goals)
            # Half-time score is a fixture field (`score["home_ht"]`/["away_ht"]),
            # present on l10 listings but not on h2h's recent_matches -- see
            # _normalize_event_row. Absent there, this simply adds nothing.
            home_ht, away_ht = score.get("home_ht"), score.get("away_ht")
            if home_ht is not None and away_ht is not None:
                goal_values["goals_1h_total"] = float(home_ht) + float(away_ht)
                goal_values["goals_2h_total"] = (
                    float(home_goals) - float(home_ht)
                ) + (float(away_goals) - float(away_ht))
                if side is not None:
                    side_ht = float(home_ht if side == "home" else away_ht)
                    side_ft = float(home_goals if side == "home" else away_goals)
                    goal_values["goals_1h_for"] = side_ht
                    goal_values["goals_2h_for"] = side_ft - side_ht
            for name, value in _make_values(
                "bzzoiro", match_id, match_date, opponent or "unknown", goal_values,
                competition_id=match.get("competition_provider_id"),
                season_id=match.get("season"),
                side=side,
            ).items():
                outcome.add(name, value)

        if run_budget is not None and not run_budget.try_consume("bzzoiro"):
            outcome.data_gaps.append("bzzoiro: run budget exhausted mid-history")
            break
        try:
            stats, gap = _bzzoiro_match_stats(client, match_id)
        except Exception as exc:  # noqa: BLE001
            outcome.data_gaps.append(f"bzzoiro: event {match_id} stats error: {exc}")
            continue
        considered += 1
        if gap == _BZZOIRO_NO_STATS:
            without_stats += 1
            continue
        if gap:
            outcome.data_gaps.append(gap)
            continue

        combined = dict(stats.get("total") or {})
        if side is not None:
            combined.update(stats.get(side) or {})
        for name, value in _make_values(
            "bzzoiro", match_id, match_date, opponent or "unknown", combined,
            competition_id=match.get("competition_provider_id"),
            season_id=match.get("season"),
            side=side,
        ).items():
            outcome.add(name, value)

    if without_stats:
        outcome.data_gaps.append(
            f"bzzoiro: {without_stats} of {considered} {mode} matches have no published "
            f"stats (typically pre-season friendlies)"
        )
    return outcome


def fetch_bzzoiro_match_context(
    team_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
    last_n: int = 10,
    as_of_date: str = "",
) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """``({provider_event_id: (match_date, opponent_name)}, data_gaps)`` for one
    team's recent fixtures.

    Exists because ``/players/{id}/stats/`` identifies each appearance only by
    ``event_id``: no date, no opponent. Resolving those per appearance would
    cost a request each; the team's fixture listing has all of them and is
    already cached from the ``*_for`` pass, so in a normal run this is free.
    """
    gaps: list[str] = []
    if not team_id:
        return {}, ["bzzoiro: missing native team id for match context"]
    date_from, date_to = _bzzoiro_window(as_of_date)
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        matches = _bzzoiro_recent_fixtures(
            client, str(team_id), date_from, date_to, last_n, run_budget, gaps
        )
    except Exception as exc:  # noqa: BLE001
        return {}, [f"bzzoiro: match context error for team {team_id}: {exc}"]

    context: dict[str, tuple[str, str]] = {}
    for match in matches:
        match_id = str(match.get("provider_match_id") or "")
        if not match_id:
            continue
        home = match.get("home_team") or {}
        away = match.get("away_team") or {}
        opponent = (
            away.get("team_name")
            if str(home.get("provider_team_id") or "") == str(team_id)
            else home.get("team_name")
        )
        context[match_id] = (
            str(match.get("date") or ""),
            str(opponent or "unknown"),
        )
    return context, gaps


def fetch_bzzoiro_player_history(
    player_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
    last_n: int = 10,
    as_of_date: str = "",
    exclude_event_id: str = "",
    match_context: dict[str, tuple[str, str]] | None = None,
) -> FetchOutcome:
    """One player's per-match prop history, in a single provider call.

    ``/players/{id}/stats/`` returns the box scores inline and newest-first, so
    unlike the team path there is no listing-then-fetch fan-out and no ascending
    -order offset dance: ``limit=last_n`` is the last ``last_n`` appearances.
    This is the cheapest data in the whole pipeline per row it produces.

    ``match_context`` maps this provider's event id to ``(match_date,
    opponent)``. The box-score rows carry neither -- only ``event_id`` -- and
    resolving each one would cost a request per appearance, so the caller passes
    the map it already built from the team's fixture history. An appearance
    outside that map is still kept, with an empty date: a prop's whole value is
    its sample, and the observation is real whether or not we can name the
    opponent.

    Appearances with no minutes are dropped. A substitute who did not come on
    has a box score of zeroes, and counting those would make every UNDER prop
    look like a lock -- the same defect that mapping one player's aces onto
    ``aces_total`` produced for tennis.
    """
    outcome = FetchOutcome()
    if not player_id:
        outcome.data_gaps.append("bzzoiro: missing native player id")
        return outcome
    if run_budget is not None and not run_budget.try_consume("bzzoiro"):
        outcome.data_gaps.append("bzzoiro: run budget exhausted before player history")
        return outcome

    date_from, date_to = _bzzoiro_window(as_of_date)
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        result = client.get_player_stats_result(
            player_id, date_from=date_from, date_to=date_to, limit=last_n
        )
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"bzzoiro: player {player_id} history error: {exc}")
        return outcome

    if result.status not in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
        status_label = getattr(result.status, "value", str(result.status))
        outcome.data_gaps.append(
            f"bzzoiro: {status_label} history for player {player_id}"
        )
        return outcome

    context = match_context or {}
    appearances = (result.value or {}).get("appearances") or []
    played = 0
    for appearance in appearances:
        match_id = str(appearance.get("provider_match_id") or "")
        if not match_id or match_id == str(exclude_event_id):
            continue
        if not (appearance.get("minutes_played") or 0):
            continue
        played += 1
        match_date, opponent = context.get(match_id, ("", "unknown"))
        raw_metrics = appearance.get("metrics") or {}
        metrics = {
            _BZZOIRO_PLAYER_ALIASES[name]: value
            for name, value in raw_metrics.items()
            if name in _BZZOIRO_PLAYER_ALIASES
        }
        card_parts = [raw_metrics[key] for key in _BZZOIRO_PLAYER_CARD_KEYS if key in raw_metrics]
        if card_parts:
            metrics[_BZZOIRO_PLAYER_CARDS_METRIC] = float(sum(card_parts))
        # No ``side``: player props are out of this field's scope on purpose.
        # ``match_context`` is keyed by match id and merged across *both* of
        # tonight's teams, so the venue stored against an id would be whichever
        # team's pass wrote it last -- already true of ``opponent``, and
        # tolerable there because a wrong opponent name is inert. A wrong
        # venue would not be: the only consumer is a per-team rule
        # (``context_flags._venue_flag``), which reads team buckets and never
        # this one.
        for name, value in _make_values(
            "bzzoiro", match_id, match_date, opponent or "unknown", metrics
        ).items():
            outcome.add(name, value)

    if not played:
        outcome.data_gaps.append(
            f"bzzoiro: player {player_id} has no appearance with minutes in the window"
        )
    return outcome


def fetch_bzzoiro_lineup(
    event_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
) -> tuple[str, dict[str, list[dict]], list[str]]:
    """``(lineup_status, {"home": [...], "away": [...]}, data_gaps)``.

    ``lineup_status`` is ``"confirmed"`` once the teams announce and
    ``"predicted"`` before that. Both are returned, and the status is passed on
    rather than used to filter here: a prop off a predicted XI is a real read
    with a weaker premise, and dropping it would mean no props at all until an
    hour before kickoff -- which is after the lines worth betting have moved.
    Which one it was is recorded on every row it produces.
    """
    gaps: list[str] = []
    if not event_id:
        return "", {}, ["bzzoiro: missing native event id for lineups"]
    if run_budget is not None and not run_budget.try_consume("bzzoiro"):
        return "", {}, ["bzzoiro: run budget exhausted before lineups"]
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        result = client.get_lineups_result(event_id)
    except Exception as exc:  # noqa: BLE001
        return "", {}, [f"bzzoiro: lineup error for event {event_id}: {exc}"]

    if result.status is not SourceResultStatus.SUCCESS or not result.value:
        status_label = getattr(result.status, "value", str(result.status))
        return "", {}, [f"bzzoiro: {status_label} lineups for event {event_id}"]

    sides = result.value.get("sides") or {}
    players = {
        side: list((sides.get(side) or {}).get("players") or [])
        for side in ("home", "away")
    }
    return str(result.value.get("lineup_status") or ""), players, gaps


# referee_id -> parsed profile, or None when the provider had nothing usable.
#
# Process-wide, and the reason this is worth caching at all: an official works
# many fixtures across a season, so a slate that spans two rounds of the same
# league hits the same referee repeatedly. A negative answer is cached too --
# re-asking about a referee below the provider's five-match publication floor
# spends a request to be told "nothing" a second time.
_BZZOIRO_REFEREE_CACHE: dict[str, dict[str, Any] | None] = {}


def reset_bzzoiro_referee_cache() -> None:
    """Forget resolved referee profiles. For tests, and for a long-lived process
    that should not carry one betting day's officials into the next."""
    _BZZOIRO_REFEREE_CACHE.clear()


def fetch_bzzoiro_referee(
    referee_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """``(referee_profile | None, data_gaps)`` for one official.

    Context, not a sample. The averages describe the referee's season, not this
    fixture, so nothing here may reach ``p_low`` -- it is read beside the cards
    and fouls rows the way ``tipster`` and ``market_signal`` are.

    That said it is the only thing in the pipeline that speaks to those two
    markets from outside the two clubs' own histories, which is why it is worth
    a call: officials in one competition differ by roughly a third of a cards
    line, and the fixture's ``referee_id`` is already in hand for free.
    """
    if not referee_id:
        return None, []
    if referee_id in _BZZOIRO_REFEREE_CACHE:
        return _BZZOIRO_REFEREE_CACHE[referee_id], []
    if run_budget is not None and not run_budget.try_consume("bzzoiro"):
        return None, ["bzzoiro: run budget exhausted before referee profile"]
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        result = client.get_referee_result(referee_id)
    except Exception as exc:  # noqa: BLE001 - one referee must not abort the event
        return None, [f"bzzoiro: referee error for {referee_id}: {exc}"]

    if result.status is not SourceResultStatus.SUCCESS or not result.value:
        status_label = getattr(result.status, "value", str(result.status))
        _BZZOIRO_REFEREE_CACHE[referee_id] = None
        return None, [f"bzzoiro: {status_label} referee profile for {referee_id}"]

    profile = result.value.get("referee")
    profile = profile if isinstance(profile, dict) else None
    _BZZOIRO_REFEREE_CACHE[referee_id] = profile
    return profile, []


# league_id -> {team_id: standings row}, or None when the provider had nothing.
#
# Cached hard, because the win is the ratio: a slate is dozens of fixtures drawn
# from a handful of competitions, and a league table is identical for every
# fixture in it. One call per league, not per team and not per event.
_BZZOIRO_STANDINGS_CACHE: dict[str, dict[str, Any] | None] = {}


def reset_bzzoiro_standings_cache() -> None:
    """Forget resolved league tables. For tests, and for a long-lived process
    that should not serve yesterday's table to today's fixtures."""
    _BZZOIRO_STANDINGS_CACHE.clear()


def fetch_bzzoiro_league_table(
    league_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """``({team_id: row}, data_gaps)`` for one competition's table.

    Worth the call for one field the pipeline has nowhere else: **season xG**.
    Everything else it holds is per finished match, so a side's underlying
    quality has to be re-derived from the same ten observations a hit rate is
    already counted from -- which is not a second opinion, it is the same
    opinion twice.

    Context, not a sample. ``xgf``/``xga`` describe a season; they never enter
    ``p_low``. ``xg_games`` travels with them so a two-match figure cannot pass
    for a settled one.
    """
    if not league_id:
        return None, []
    if league_id in _BZZOIRO_STANDINGS_CACHE:
        return _BZZOIRO_STANDINGS_CACHE[league_id], []
    if run_budget is not None and not run_budget.try_consume("bzzoiro"):
        return None, ["bzzoiro: run budget exhausted before league table"]
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        result = client.get_standings_result(league_id)
    except Exception as exc:  # noqa: BLE001 - one league must not abort the run
        return None, [f"bzzoiro: standings error for league {league_id}: {exc}"]

    if result.status is not SourceResultStatus.SUCCESS or not result.value:
        status_label = getattr(result.status, "value", str(result.status))
        _BZZOIRO_STANDINGS_CACHE[league_id] = None
        return None, [f"bzzoiro: {status_label} standings for league {league_id}"]

    table = result.value.get("table")
    table = table if isinstance(table, dict) else None
    _BZZOIRO_STANDINGS_CACHE[league_id] = table
    return table, []


def fetch_bzzoiro_squad_availability(
    team_id: str,
    side: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """``(availability_block | None, data_gaps)`` for one side's squad.

    Deliberately **not** cached across the run. A squad's injury list is the one
    thing here that moves during a betting day, and two fixtures for the same
    club on one date is not a case worth trading freshness for.
    """
    if not team_id:
        return None, []
    if run_budget is not None and not run_budget.try_consume("bzzoiro"):
        return None, [f"bzzoiro: run budget exhausted before {side} squad"]
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        result = client.get_team_squad_result(team_id)
    except Exception as exc:  # noqa: BLE001 - one squad must not abort the event
        return None, [f"bzzoiro: squad error for team {team_id}: {exc}"]

    if result.status is not SourceResultStatus.SUCCESS or not result.value:
        status_label = getattr(result.status, "value", str(result.status))
        return None, [f"bzzoiro: {status_label} squad for team {team_id}"]

    value = result.value
    return {
        "provider_team_id": str(value.get("provider_team_id") or team_id),
        "side": side,
        "squad_size": int(value.get("squad_size") or 0),
        "unavailable_count": int(value.get("unavailable_count") or 0),
        "availability_unknown_count": int(value.get("availability_unknown_count") or 0),
        "unavailable": list(value.get("unavailable") or []),
    }, []


# team_id -> its current competition's native id, or None when the provider had
# nothing usable. Cached hard, like the referee and standings tables: a club's
# competition does not change intra-day.
#
# There is no team-detail endpoint that carries this (verified live,
# 2026-08-31: ``get_team_detail`` returns only id/name/short_name/country/
# venue_id -- no league field, despite its own description promising a coach
# and social items it also does not return). The only place a team's current
# league id appears is its own fixtures listing (``competition_provider_id`` on
# each normalized row, bzzoiro.py's ``_normalize_event_row``), so this reads
# that -- the same listing and the same process-wide ``_BZZOIRO_FIXTURES_CACHE``
# ``fetch_bzzoiro_history`` already populates for the l10 metrics fetch. A team
# whose bzzoiro fixtures were already pulled for its own metrics resolves its
# league for free; only a team reached solely through another provider's
# discovery (the actual Faza 5a gap) pays a fresh listing call.
_BZZOIRO_TEAM_LEAGUE_CACHE: dict[str, str | None] = {}


def reset_bzzoiro_team_league_cache() -> None:
    """Forget resolved team->league ids. For tests, and for a long-lived
    process that should not carry one betting day's season into the next."""
    _BZZOIRO_TEAM_LEAGUE_CACHE.clear()


def fetch_bzzoiro_team_league_id(
    team_id: str,
    as_of_date: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
) -> tuple[str | None, list[str]]:
    """``(league_id | None, data_gaps)`` for one team, from its own fixtures.

    Backfill path for ``FixtureContext.league_id``, which discovery only sets
    for fixtures bzzoiro itself found (docs/PLAN_BOGATE_STATYSTYKI.md Faza 5a:
    25/192 football matches on the 2026-08-31 run). Every other fixture still
    has a resolvable bzzoiro team id once name-matching has run, just no
    league -- this is what lets ``season_form`` reach the rest of them.
    """
    if not team_id:
        return None, []
    if team_id in _BZZOIRO_TEAM_LEAGUE_CACHE:
        return _BZZOIRO_TEAM_LEAGUE_CACHE[team_id], []
    date_from, date_to = _bzzoiro_window(as_of_date)
    gaps: list[str] = []
    try:
        client = get_client("bzzoiro", rate_limiter=rate_limiter)
        matches = _bzzoiro_recent_fixtures(
            client, str(team_id), date_from, date_to, 10, run_budget, gaps
        )
    except Exception as exc:  # noqa: BLE001 - one team must not abort the event
        return None, [f"bzzoiro: team league lookup error for team {team_id}: {exc}"]

    # A team with no resolvable competition id in its recent fixtures (as
    # opposed to a fetch failure, which already added its own gap above) is a
    # real, silent provider state -- same convention `fetch_bzzoiro_league_table`
    # follows for an empty-but-successful table.
    league_id = next(
        (str(m["competition_provider_id"]) for m in matches if m.get("competition_provider_id")),
        None,
    )
    _BZZOIRO_TEAM_LEAGUE_CACHE[team_id] = league_id
    return league_id, gaps


# Shortest token pairing that can anchor a team match on its own. Three, not
# four: "Man Utd" / "Manchester United" abbreviates *every* token, so a 4+
# floor rejects it, while the false positives this guard exists for are all
# two-letter fragments ("sp" in "southampton", "be" in "barnsley").
_SUBSTANTIVE_TOKEN_LEN = 3


def _token_matches(one: str, two: str) -> bool:
    """Whether two team-name tokens denote the same word.

    Flashscore contracts words that other providers spell out ("Utd" for
    "United", "Atl." for "Atletico", "Dep." for "Deportivo"), so a plain
    equality check drops most of its history. A short token counts as a match
    when it is a prefix or an in-order subsequence of the longer one.
    """
    if one == two:
        return True
    short, long = (one, two) if len(one) <= len(two) else (two, one)
    # Two-letter contractions are real and common ("Ulsan HD" for "Ulsan
    # Hyundai"). They are safe to accept here only because _team_matches
    # additionally requires some pairing to be anchored on both sides by
    # _SUBSTANTIVE_TOKEN_LEN characters, so "Botafogo-SP" still never matches
    # "Botafogo RJ".
    if len(short) < 2:
        return False
    # A contraction keeps the word's first letter ("Utd"/"United",
    # "Atl."/"Atletico", "Dep."/"Deportivo"). Without that anchor the
    # subsequence test below accepts any short token whose letters merely
    # appear in order somewhere inside the longer one -- "al" inside "basel",
    # which is how every Saudi side of 2026-08-25 matched FC Basel's season.
    if short[0] != long[0]:
        return False
    if long.startswith(short):
        return True
    iterator = iter(long)
    if all(ch in iterator for ch in short):
        return True
    return SequenceMatcher(None, short, long).ratio() >= 0.85


def _team_matches(one: str, two: str) -> bool:
    """Whether two normalized team names refer to the same team.

    Every token of the shorter name must match some token of the longer, and at
    least one pairing must be substantive on *both* sides -- so "Real Betis"
    matches "Betis" and "Manchester Utd" matches "Manchester United", while
    "Botafogo-SP" does not match "Botafogo RJ".

    Measuring the anchor on both sides, rather than on either side, is what
    stops a two-letter fragment from carrying a whole name: "sp" is a
    subsequence of "southampton" and "be" (split off "Be'er" by the
    apostrophe) of "barnsley", and with the anchor satisfied by the long side
    alone those two counted as team identity. Shorter tokens can still
    participate in a pairing -- "Ulsan HD" matches "Ulsan Hyundai" on "Ulsan"
    -- they just cannot be the only thing holding the match together.
    """
    if not one or not two:
        return False
    if one == two:
        return True
    tokens_one, tokens_two = one.split(), two.split()
    short, long = (tokens_one, tokens_two) if len(tokens_one) <= len(tokens_two) else (tokens_two, tokens_one)
    matched_substantive = False
    for token in short:
        partner = next((other for other in long if _token_matches(token, other)), None)
        if partner is None:
            return False
        if min(len(token), len(partner)) >= _SUBSTANTIVE_TOKEN_LEN:
            matched_substantive = True
    return matched_substantive


def _normalize_team_name(name: str) -> str:
    """Fold a team name to a comparable key. SportDB/Flashscore abbreviate
    ("Manchester Utd", "Brighton") where discovery sources spell out
    ("Manchester United", "Brighton and Hove Albion"), so common suffixes and
    punctuation are stripped before comparison."""
    tokens = [t for t in _fold(name).split() if t not in _TEAM_NAME_STOPWORDS]
    return " ".join(tokens)


_TEAM_NAME_STOPWORDS = frozenset(
    {"fc", "cf", "afc", "sc", "ac", "club", "the", "and", "de", "cd", "ss", "as", "us"}
)

# Season-results listings are identical for every event in the same league, so
# one process-wide cache keyed by (competition, season) keeps a multi-event run
# from re-paging the same league once per event.
_SPORTDB_SEASON_CACHE: dict[tuple[str, str], list[dict]] = {}
_SPORTDB_SEASON_CACHE_LOCK = threading.Lock()
_SPORTDB_KEY_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_SPORTDB_MAX_RESULT_PAGES = 3

# Historical matches older than this are dropped from an L10/H2H sample.
# api-football's free tier answers get_team_last_fixtures with fixtures from
# seasons it still has cached -- 2024 matches came back for a 2026 fixture --
# and pooling two-year-old form with current form produces a hit rate that
# describes neither. 500 days keeps a full previous season while excluding that.
_MAX_OBSERVATION_AGE_DAYS = 500


def _is_recent(match_date: str) -> bool:
    """Whether an ISO-ish date string is inside the observation window. A date
    we cannot parse is kept: dropping it would silently discard providers whose
    date format we have not seen."""
    if not match_date:
        return True
    try:
        parsed = datetime.fromisoformat(match_date[:19].replace("Z", ""))
    except ValueError:
        try:
            parsed = datetime.strptime(match_date[:10], "%Y-%m-%d")
        except ValueError:
            return True
    age = (datetime.now(UTC).replace(tzinfo=None) - parsed).days
    return age <= _MAX_OBSERVATION_AGE_DAYS

# Minimum score for _sportdb_competition_refs to accept a search hit. A
# country-name match adds 0.6, so any genuine country-qualified hit clears this
# comfortably, while a merely similar-sounding league in an unrelated country
# ("La Liga" -> Argentina's "Liga A", ratio 0.72) does not.
#
# This number is a filter, not a guarantee, and it is deliberately not being
# raised. Name distance cannot separate "Saudi Pro League" from Switzerland's
# "Super League" (0.786) or Belgium's "Pro League" (0.769) -- every threshold
# that excludes one admits the other. What actually keeps foreign-league
# history out is _league_fields_either_team, which checks the resolved season's
# participants instead of its label.
_COMPETITION_MATCH_THRESHOLD = 0.75


# Letters that NFKD does not decompose into base + combining mark, so the
# [^a-z0-9] strip below would delete them outright: "Bodo/Glimt" spelled with
# the Norwegian slashed o folded to "bod glimt", and that three-letter remnant
# then matched "Brentford".
_TRANSLITERATIONS = str.maketrans(
    {
        "\u00f8": "o", "\u00d8": "o",    # o-slash   (Bodo/Glimt, Aalesund)
        "\u00e6": "ae", "\u00c6": "ae",  # ae
        "\u0153": "oe", "\u0152": "oe",  # oe
        "\u00df": "ss",                  # sharp s
        "\u0111": "d", "\u0110": "d",    # d-stroke  (Dinamo Zagreb rosters)
        "\u00f0": "d", "\u00d0": "d",    # eth
        "\u0142": "l", "\u0141": "l",    # l-stroke  (Legia, Lech Poznan)
        "\u0131": "i", "\u0130": "i",    # dotless/dotted i (Turkish sides)
        "\u00fe": "th", "\u00de": "th",  # thorn
    }
)


def _fold(text: str) -> str:
    """Lowercase, strip diacritics and punctuation: "Brazil Série B" -> "brazil serie b"."""
    translated = (text or "").translate(_TRANSLITERATIONS)
    decomposed = unicodedata.normalize("NFKD", translated)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).split())


def _season_candidates(season: str) -> list[str]:
    """Season labels to try, in order.

    Flashscore labels European seasons by span ("2025-2026") but calendar-year
    leagues -- Brazil, MLS, the Nordics -- by year alone ("2026"), and its
    "current" season sometimes lags the calendar. Trying the span implied by
    kickoff, the previous span, then both bare years covers every layout in use
    without needing a per-league table.
    """
    candidates = [season]
    try:
        start = int(season.split("-")[0])
    except (ValueError, IndexError):
        return candidates
    for candidate in (f"{start - 1}-{start}", str(start), str(start - 1)):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _sportdb_season_results(client: Any, competition: str, season: str) -> list[dict]:
    """Raw finished-match rows for a competition season, cached per process.

    The raw rows are used rather than
    ``get_competition_results_with_evidence``'s normalized ones because that
    normalizer emits ``home_name``/``away_name`` as ``None`` for live payloads
    (whose keys are ``homeName``/``awayName``), and without team names there is
    no way to tell which historical matches belong to the event's teams.
    """
    cache_key = (competition.lower(), season)
    with _SPORTDB_SEASON_CACHE_LOCK:
        cached = _SPORTDB_SEASON_CACHE.get(cache_key)
        if cached is not None:
            return cached
        # One lock per (competition, season) so the three concurrent slots
        # (team_a / team_b / h2h) of the same event do not each page the same
        # league; the two that lose the race wait and then read the cache.
        key_lock = _SPORTDB_KEY_LOCKS.setdefault(cache_key, threading.Lock())

    with key_lock:
        with _SPORTDB_SEASON_CACHE_LOCK:
            cached = _SPORTDB_SEASON_CACHE.get(cache_key)
        if cached is not None:
            return cached

        refs = _sportdb_competition_refs(client, competition)
        rows: list[dict] = []
        if refs is not None:
            # Flashscore labels a season by its start year, and its "current"
            # season can lag the calendar, so try the season the kickoff date
            # implies and then the previous one.
            for candidate in _season_candidates(season):
                for page in range(1, _SPORTDB_MAX_RESULT_PAGES + 1):
                    payload = client.call_tool(
                        "flashscore_get_competition_results",
                        {**refs, "season": candidate, "page": page},
                    )
                    data = payload.get("data") if isinstance(payload, dict) else None
                    if not isinstance(data, list) or not data:
                        break
                    rows.extend(r for r in data if isinstance(r, dict))
                    if len(data) < 50:
                        break
                if rows:
                    break

        # Only a non-empty result is cached. Caching an empty list would let one
        # transient MCP failure suppress SportDB for that league for the rest of
        # the run, which reads as "this league has no data" rather than "one
        # call failed".
        if rows:
            with _SPORTDB_SEASON_CACHE_LOCK:
                _SPORTDB_SEASON_CACHE[cache_key] = rows
        return rows


def _league_fields_either_team(rows: list[dict], target: str, other: str) -> bool | None:
    """Whether either side of today's fixture actually appears in the season
    results that were resolved for it. ``None`` means the question could not be
    asked, because no row carried a readable team name.

    This is the check that catches a mis-resolved competition, and the point of
    it is that it never looks at the league's *name*. On 2026-08-25
    "Saudi Pro League" scored 0.786 against Switzerland's "Super League" -- the
    Swiss top flight is called literally that -- and every Saudi event of the
    day was served FC Basel's season as history. Raising
    _COMPETITION_MATCH_THRESHOLD does not close that: 0.80 still admits
    Belgium's "Pro League" at 0.769, and every new threshold buys one more
    collision. Asking the resolved season whether it contains either of the two
    teams cannot be tuned around, because it consults the data rather than the
    label.

    Either side suffices, not both: in the opening weeks of a season -- and
    whenever _season_candidates has fallen back to the previous one -- a newly
    promoted side legitimately has no rows yet, and rejecting the league over
    that would discard good data.
    """
    saw_any_name = False
    for row in rows:
        for side in ("homeName", "awayName"):
            name = _normalize_team_name(str(row.get(side) or ""))
            if not name:
                continue
            saw_any_name = True
            if _team_matches(name, target):
                return True
            if other and _team_matches(name, other):
                return True
    # No row carried a readable team name at all. That is a payload-shape
    # change (the normalizer already has to cope with homeName vs home_name),
    # not evidence about which league this is, and reporting it as "wrong
    # league" would send the next reader looking in the wrong place.
    return None if not saw_any_name else False


def fetch_sportdb_match(
    match_id: str,
    opponent_name: str,
    sportdb_adapter: SportDBMCPShadowAdapter | None = None,
    run_budget: RunBudget | None = None,
    match_date: str = "",
    rate_limiter: RateLimiter | None = None,
) -> FetchOutcome:
    """Fetch one specific match's canonical totals from SportDB, via the
    ``*_with_evidence`` variant only (docs/PIPELINE_SIMPLIFICATION_PLAN.md
    section 3)."""
    outcome = FetchOutcome()
    if run_budget is not None and not run_budget.try_consume("sportdb"):
        outcome.data_gaps.append("sportdb: run budget exhausted")
        return outcome
    # SportDBMCPClient never touches RateLimiter itself, so without this the
    # "sportdb" daily entry in API_DAILY_LIMITS would be a number nothing
    # enforces. Gating and recording here is what makes the durable
    # between-runs budget of plan section 7 real for this provider.
    if rate_limiter is not None and not rate_limiter.can_request("sportdb", 1):
        outcome.data_gaps.append("sportdb: daily quota exhausted")
        return outcome
    try:
        adapter = sportdb_adapter or SportDBMCPShadowAdapter()
        result = adapter.get_match_stats_with_evidence(match_id=match_id)
        if rate_limiter is not None:
            rate_limiter.record_request("sportdb", "flashscore_get_match_stats", 1)
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"sportdb: {exc}")
        return outcome
    if result.status != SourceResultStatus.SUCCESS or not result.value:
        status_label = getattr(result.status, "value", str(result.status))
        outcome.data_gaps.append(f"sportdb: {status_label} for match {match_id}")
        return outcome
    raw_result = result.value.get("raw_result") if isinstance(result.value, dict) else None
    combined = normalize_sportdb_match_stats(raw_result) if isinstance(raw_result, dict) else {}
    if not combined:
        outcome.data_gaps.append(f"sportdb: no recognized stats for match {match_id}")
        return outcome
    # No ``side``: this path is handed one match id and an opponent name by
    # its caller and never sees a fixture row, so which side is which is not
    # knowable here. Venue stays None, which reads as "not stated".
    for name, value in _make_values(
        "sportdb", match_id, match_date or _now_iso(), opponent_name, combined
    ).items():
        outcome.add(name, value)
    return outcome


_SPORTDB_COUNTRIES_CACHE: list[dict] | None = None
_SPORTDB_COUNTRIES_LOCK = threading.Lock()


def _sportdb_countries(client: Any) -> list[dict]:
    """All football countries Flashscore knows, fetched once per process."""
    global _SPORTDB_COUNTRIES_CACHE
    with _SPORTDB_COUNTRIES_LOCK:
        if _SPORTDB_COUNTRIES_CACHE is not None:
            return _SPORTDB_COUNTRIES_CACHE
    payload = client.call_tool("flashscore_list_countries", {"sport": "football"})
    data = payload.get("data") if isinstance(payload, dict) else None
    countries = [c for c in (data or []) if isinstance(c, dict)]
    with _SPORTDB_COUNTRIES_LOCK:
        _SPORTDB_COUNTRIES_CACHE = countries
    return countries


def _country_in_query(client: Any, query: str) -> dict | None:
    """The Flashscore country whose name appears in ``query`` as whole tokens,
    longest name first so "Bosnia and Herzegovina" beats a stray "Bosnia"."""
    tokens = f" {query} "
    best = None
    best_len = 0
    for country in _sportdb_countries(client):
        name = _fold(str(country.get("name") or ""))
        if not name or len(name) < 4:
            continue
        if f" {name} " in tokens and len(name) > best_len:
            best, best_len = country, len(name)
    return best


# Credit for a candidate whose own country name shares a whole word with the
# query, when the full country name is absent so _country_in_query found
# nothing. "Saudi Pro League" names its country by short form only, and the
# search path was scoring the name alone: Switzerland's and China's "Super
# League" both took 0.800 while the correct "Saudi Professional League"
# (country "Saudi Arabia") came third at 0.757.
#
# Sized to break ties between plausible candidates, not to promote implausible
# ones: closing that particular gap needs 0.05, and at 0.10 a genuinely weak
# 0.55 match still lands at 0.65 and is still rejected. A larger bonus would
# start lifting wrong-competition-right-country hits ("Saudi Super Cup" for
# "Saudi Pro League") over the threshold.
_PARTIAL_COUNTRY_BONUS = 0.10


def _shares_country_token(query: str, country_name: str) -> bool:
    """Whether the query and a candidate's country name share a substantive
    whole word ("saudi" from "Saudi Arabia"). Whole tokens only, no fuzz: this
    is meant to read a country the query already names, not to guess one."""
    if not country_name:
        return False
    country_tokens = {t for t in country_name.split() if len(t) >= 4}
    return bool(country_tokens & set(query.split()))


def _ref_candidate(item: dict, query: str, country_name: str) -> tuple[float, dict[str, Any]] | None:
    """Score one competition candidate against the query, returning
    (score, structured refs) or None if its link cannot be parsed."""
    # link shape: /api/flashscore/football/england:198/premier-league:dYlOSQOD
    parts = [p for p in str(item.get("link") or "").split("/") if p]
    if len(parts) < 4 or ":" not in parts[-1] or ":" not in parts[-2]:
        return None
    country_slug, _, country_id = parts[-2].partition(":")
    competition_slug, _, competition_id = parts[-1].partition(":")
    if not (country_slug and country_id and competition_slug and competition_id):
        return None

    country_hit = bool(country_name) and country_name in query
    # Compare league names with the country stripped out, so "La Liga - Spain"
    # is matched against "LaLiga" rather than against "LaLiga Spain".
    bare_query = query.replace(country_name, "").strip() if country_hit else query
    name = _fold(str(item.get("name") or ""))
    score = SequenceMatcher(None, bare_query.replace(" ", ""), name.replace(" ", "")).ratio()
    if country_hit:
        score += 0.6
    elif _shares_country_token(query, country_name):
        score += _PARTIAL_COUNTRY_BONUS

    try:
        country_id_value: Any = int(country_id)
    except ValueError:
        country_id_value = (item.get("country") or {}).get("id")
    return score, {
        "sport": "football",
        "country_slug": country_slug,
        "country_id": country_id_value,
        "competition_slug": competition_slug,
        "competition_id": competition_id,
    }


_COMPETITION_MAP_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "sportdb_competition_map.json"
)
_COMPETITION_MAP_CACHE: dict[str, dict[str, Any]] | None = None
_COMPETITION_MAP_LOCK = threading.Lock()


def _pinned_competition_map() -> dict[str, dict[str, Any]]:
    """The verified entries of config/sportdb_competition_map.json, keyed by
    folded competition name. Read once per process.

    Only entries carrying both ``refs`` and a ``verification`` block are
    returned: a seed with no verification is a to-do, and treating it as a pin
    would be exactly the unproven guess the map exists to eliminate. A missing
    or malformed file yields an empty map rather than raising -- config trouble
    must degrade the resolver to its search path, not abort the run.
    """
    global _COMPETITION_MAP_CACHE
    with _COMPETITION_MAP_LOCK:
        if _COMPETITION_MAP_CACHE is not None:
            return _COMPETITION_MAP_CACHE
    pinned: dict[str, dict[str, Any]] = {}
    try:
        document = json.loads(_COMPETITION_MAP_PATH.read_text(encoding="utf-8"))
        for key, entry in (document.get("competitions") or {}).items():
            refs = entry.get("refs")
            if isinstance(refs, dict) and entry.get("verification"):
                pinned[_fold(key)] = refs
    except (OSError, ValueError, AttributeError):
        pinned = {}
    with _COMPETITION_MAP_LOCK:
        if _COMPETITION_MAP_CACHE is None:
            _COMPETITION_MAP_CACHE = pinned
        return _COMPETITION_MAP_CACHE


def _sportdb_competition_refs(client: Any, competition: str) -> dict[str, Any] | None:
    """Resolve a free-text competition name to the structured refs
    flashscore_get_competition_results requires (sport / country_slug /
    country_id / competition_slug / competition_id).

    config/sportdb_competition_map.json is consulted first and answers most
    slates outright. Everything below it is the fallback for a league nobody
    has pinned yet -- worth keeping, because an unpinned league should still
    return data, but it is a guess and the map is not. To pin a new league, add
    a seed there and run scripts/simple/build_sportdb_competition_map.py; do
    not tune the scoring below to accommodate it.

    When the name carries a country ("La Liga - Spain", "Brazil Série B"), that
    country's full competition list is enumerated and matched deterministically;
    ``flashscore_search`` is only the fallback for names that name no country.
    The search tool matches the literal query string and orders by its own
    relevance, which is routinely wrong here -- it answers "La Liga - Spain"
    with Liga MX (Mexico) first and "Brazil Série B" with Serie A (Italy) first,
    and finds no Spanish league at all unless the punctuation is removed.
    Candidates are therefore always scored, and a weak best match is rejected
    outright: no data beats data from the wrong league.

    Neither listing tool has a ``*_with_evidence`` wrapper on
    SportDBMCPShadowAdapter -- only the fixed, config-pinned competition from
    certification/football/*_mapping_summary.json does -- so the raw tools are
    called here. Section 3's uniform-error-contract requirement still holds:
    every caller of this module gets a FetchOutcome, because fetch_sportdb_history
    converts any raise into a data_gap.
    """
    query = _fold(competition)
    if not query:
        return None

    # A pinned league is a lookup, not a guess: its refs were written only
    # after that country's real season results were shown to contain clubs
    # asserted by hand. Nothing fuzzy participates, and it costs no call.
    pinned = _pinned_competition_map().get(query)
    if pinned is not None:
        return dict(pinned)

    candidates: list[tuple[dict, str]] = []
    country = _country_in_query(client, query)
    if country is not None:
        payload = client.call_tool(
            "flashscore_list_competitions",
            {
                "sport": "football",
                "country_slug": country.get("slug"),
                "country_id": country.get("id"),
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        country_name = _fold(str(country.get("name") or ""))
        candidates.extend((c, country_name) for c in (data or []) if isinstance(c, dict))

    if not candidates:
        payload = client.call_tool("flashscore_search", {"q": competition, "type": "competition"})
        data = payload.get("data") if isinstance(payload, dict) else None
        found = (data or {}).get("results") if isinstance(data, dict) else None
        candidates.extend(
            (c, _fold(str((c.get("country") or {}).get("name") or "")))
            for c in (found or [])
            if isinstance(c, dict)
        )

    best_refs: dict[str, Any] | None = None
    best_score = 0.0
    for item, country_name in candidates:
        scored = _ref_candidate(item, query, country_name)
        if scored is None:
            continue
        score, refs = scored
        if score > best_score:
            best_score, best_refs = score, refs

    return best_refs if best_score >= _COMPETITION_MATCH_THRESHOLD else None


def fetch_sportdb_history(
    team_name: str,
    opponent_name: str,
    competition: str,
    season: str,
    run_budget: RunBudget | None = None,
    last_n: int = 10,
    mode: str = "l10",
    rate_limiter: RateLimiter | None = None,
) -> FetchOutcome:
    """Historical per-match canonical totals from SportDB for one team
    (``mode="l10"``) or for a specific pairing (``mode="h2h"``).

    SportDB exposes no by-team match history endpoint (flashscore_get_team_details
    returns only a squad, verified live), so the route is: resolve the event's
    competition to structured refs, page its season results, keep the finished
    matches this team played, then pull each one's stats. Results are cached per
    (competition, season) for the process, so a 20-event slate in five leagues
    costs five listing calls, not twenty.
    """
    outcome = FetchOutcome()
    if not team_name or not competition:
        outcome.data_gaps.append("sportdb: no competition/team to resolve for history")
        return outcome

    try:
        from bet.api_clients.sportdb_mcp import SportDBMCPClient

        client = SportDBMCPClient()
        adapter = SportDBMCPShadowAdapter()
        rows = _sportdb_season_results(client, competition, season)
    except Exception as exc:  # noqa: BLE001 - incl. SportDBMCPError family (section 3)
        outcome.data_gaps.append(f"sportdb: {exc}")
        return outcome

    if not rows:
        outcome.data_gaps.append(f"sportdb: no season results for '{competition}' {season}")
        return outcome

    target = _normalize_team_name(team_name)
    other = _normalize_team_name(opponent_name)

    # No data beats data from the wrong league. A silent wrong-league dossier
    # is worse than BLOCKED: on 2026-08-25 it produced the four most confident
    # rows of the whole sheet.
    fields_either = _league_fields_either_team(rows, target, other)
    if fields_either is None:
        outcome.data_gaps.append(
            f"sportdb: season results for '{competition}' carry no readable "
            "team names -- payload shape changed, cannot verify the league"
        )
        return outcome
    if not fields_either:
        outcome.data_gaps.append(
            f"sportdb: resolved competition '{competition}' fields neither "
            f"'{team_name}' nor '{opponent_name}' -- wrong league, discarded"
        )
        return outcome

    matches = []
    for row in rows:
        home = _normalize_team_name(str(row.get("homeName") or ""))
        away = _normalize_team_name(str(row.get("awayName") or ""))
        if str(row.get("eventStage") or "").upper() != "FINISHED":
            continue
        if mode == "h2h":
            if not other:
                continue
            pairing = (
                (_team_matches(home, target) and _team_matches(away, other))
                or (_team_matches(home, other) and _team_matches(away, target))
            )
            if not pairing:
                continue
        elif not (_team_matches(home, target) or _team_matches(away, target)):
            continue
        matches.append(row)

    if not matches:
        outcome.data_gaps.append(f"sportdb: no {mode} matches for '{team_name}' in '{competition}'")
        return outcome

    matches.sort(key=lambda r: str(r.get("startDateTimeUtc") or ""), reverse=True)
    for row in matches[:last_n]:
        match_id = str(row.get("eventId") or "")
        if not match_id:
            continue
        home = _normalize_team_name(str(row.get("homeName") or ""))
        opponent = row.get("awayName") if _team_matches(home, target) else row.get("homeName")
        outcome.merge(
            fetch_sportdb_match(
                match_id,
                str(opponent or "unknown"),
                sportdb_adapter=adapter,
                run_budget=run_budget,
                match_date=str(row.get("startDateTimeUtc") or ""),
                rate_limiter=rate_limiter,
            )
        )
    return outcome


def fetch_google_sports_h2h(team_one: str, team_two: str, sport: str, rate_limiter: RateLimiter) -> FetchOutcome:
    """google-sports gives narrative H2H context only (score/date/red-card
    flag) -- never a numeric value for a canonical metric -- so this always
    returns an empty FetchOutcome.metrics. Kept for provider parity / future
    use; not called from enrich.py's metric-fetching loop."""
    outcome = FetchOutcome()
    try:
        client = get_client("google-sports", rate_limiter=rate_limiter)
        enrichment = client.get_h2h_enrichment(team_one, team_two, sport=sport)
    except Exception as exc:  # noqa: BLE001
        outcome.data_gaps.append(f"google-sports: {exc}")
        return outcome
    if not getattr(enrichment, "h2h_matches", None):
        outcome.data_gaps.append(f"google-sports: no h2h matches for '{team_one}' vs '{team_two}'")
    return outcome
