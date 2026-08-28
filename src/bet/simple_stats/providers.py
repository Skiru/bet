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
from pathlib import Path
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from bet.api_clients import get_client
from bet.api_clients.bzzoiro import FINISHED_STATUSES as BZZOIRO_FINISHED_STATUSES
from bet.api_clients.bzzoiro_tennis import (
    FINISHED_STATUSES as BZZOIRO_TENNIS_FINISHED_STATUSES,
)
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.sportdb_mcp import SportDBMCPShadowAdapter
from bet.integration.source_result import SourceResultStatus

from bet.simple_stats.contracts import ProviderValue

logger = logging.getLogger(__name__)

# Providers driven by team *name*: each exposes resolve_team_id(name) plus
# get_team_last_fixtures/get_h2h, so one generic loop covers them all.
PROVIDERS_BY_SPORT: dict[str, tuple[str, ...]] = {
    "football": ("espn-football", "api-football", "understat"),
    "tennis": ("tennis-abstract", "sackmann", "espn-tennis"),
}

# Providers that cannot be driven by team *name* and are therefore fetched
# through their own dedicated path in enrich.py, keyed off the native ids
# discovery captured (EventRecord.source_ids / .provider_team_ids):
#   highlightly -> /last-five-games, /head-2-head, /statistics/{match_id}
#   sportdb     -> flashscore competition results -> flashscore_get_match_stats
#   bzzoiro     -> /teams/{id}/fixtures, /events/{id}/, /events/{id}/stats/
#   bzzoiro-tennis -> /tennis/api/v2/matches/{id}/h2h/, /matches/{id}/
NATIVE_ID_PROVIDERS_BY_SPORT: dict[str, tuple[str, ...]] = {
    "football": ("highlightly", "sportdb", "bzzoiro"),
    # Was empty. Tennis had no native identification at all -- every provider
    # re-found both players by name through a search endpoint -- which is half
    # the reason the sport contributed almost nothing.
    "tennis": ("bzzoiro-tennis",),
}

# google-sports is intentionally not part of PROVIDERS_BY_SPORT: it only
# returns narrative H2H context (score, date, red-card flag), never a numeric
# value for one of our canonical metrics, so it has no slot in
# MetricObservation. fetch_google_sports_h2h() below exists for completeness
# / future use but is not called from enrich.py's metric-fetching loop.

_ESPN_FOOTBALL_ALIASES = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "shots": "shots_total",
    "shots_on_target": "shots_on_target_total",
    "fouls": "fouls_total",
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
# The per-team table is deliberately shorter: it covers exactly the five stats
# that have a team market in STANDARD_MARKET_LINES. A "_for" metric nobody can
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
}
# Canonical player-prop metrics, keyed by the client's normalized names. The
# client already emits this vocabulary, so this table exists to state which of
# its fields the pipeline prices, not to rename them.
_BZZOIRO_PLAYER_ALIASES = {
    "player_total_shots": "player_total_shots",
    "player_shots_on_target": "player_shots_on_target",
    "player_fouls": "player_fouls",
    "player_was_fouled": "player_was_fouled",
}
# "Player to be Carded" is a bet on *any* card, so a straight red settles it
# yes. Pricing it off yellows alone would report a carded player as not carded
# in exactly the matches where the card was most obvious, so the two are summed
# into one canonical metric rather than aliased separately. Cards are mutually
# exclusive per shown card, so the sum is the count of cards, never a
# double-count of one.
_BZZOIRO_PLAYER_CARD_KEYS = ("player_yellow_cards", "player_red_cards")
_BZZOIRO_PLAYER_CARDS_METRIC = "player_cards"

# Bzzoiro's tennis box score is already ``p1_*``/``p2_*``, so unlike football
# corners this provider arrives with the per-player split in the same wave.
#
# Match totals: both players summed, matching how STANDARD_MARKET_LINES phrases
# "Total Aces". ``total_sets`` and ``breaks_total`` are derived rather than
# aliased and are handled in _bzzoiro_tennis_match_metrics.
_BZZOIRO_TENNIS_TOTAL_ALIASES = {
    "aces": "aces_total",
    "double_faults": "double_faults_total",
    "games_won": "total_games",
}
# One player's own line. These reuse the canonical names tennis already had --
# ``first_serve_pct`` is a property of a server, never of a match, and
# tennis-abstract already reports it for the player it was asked about, so the
# same name in the same slot means the same thing and the two can corroborate.
_BZZOIRO_TENNIS_PLAYER_ALIASES = {
    "aces": "aces_for",
    "double_faults": "double_faults_for",
    "games_won": "games_won",
    "first_serve_pct": "first_serve_pct",
    "first_serve_won_pct": "first_serve_won_pct",
    "break_points_saved_pct": "break_points_saved_pct",
    "break_points_converted_pct": "break_points_converted_pct",
}

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

# H2H is only wired for providers whose get_h2h returns a flat, normalized
# meeting shape ({"id"/"fixture_id", "date", ...}). api-football's get_h2h
# returns raw provider payload items nested under "fixture", which this
# generic path does not attempt to parse (section 4.1: api-football is a
# supplementary cross-check, not a primary H2H source).
_H2H_SUPPORTED_PROVIDERS = frozenset({"espn-football", "espn-tennis", "tennis-abstract", "sackmann"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
#
# bzzoiro-tennis is deliberately absent: its daily ceiling is 95, below the
# shared 100 default, so a run-level override could only ever raise a limit the
# daily counter already enforces more tightly.
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

    def merge(self, other: "FetchOutcome") -> None:
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

    ``total_games`` is derived rather than read: a tennis match's total games
    is the games this player served plus the games they returned, and
    tennis-abstract exposes exactly those two counts (``service_games`` /
    ``return_games``). Without this derivation ``total_games`` -- one of
    tennis's three PRIORITY_METRICS and the stat behind the "Total Games"
    market in STANDARD_MARKET_LINES -- would never be populated at all.
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

    service_games = stats.get("service_games")
    return_games = stats.get("return_games")
    try:
        if service_games is not None and return_games is not None:
            total = float(service_games) + float(return_games)
            if total > 0:
                out["total_games"] = total
    except (TypeError, ValueError):
        pass
    return out


def _combine_stats(provider_key: str, stats: dict, aliases: dict[str, str]) -> dict[str, float]:
    """Pick the right combiner for a provider's stats-dict shape."""
    if provider_key in _FLAT_STAT_PROVIDERS:
        return _flat_from_dict_stats(stats, aliases)
    return _combined_from_dict_stats(stats, aliases)


def _make_values(
    provider: str, match_id: Any, match_date: str, opponent: str, combined: dict[str, float]
) -> dict[str, ProviderValue]:
    if not _is_recent(match_date):
        return {}
    observed_at = _now_iso()
    return {
        name: ProviderValue(
            provider=provider,
            match_id=str(match_id),
            match_date=match_date or "",
            opponent=opponent or "unknown",
            value=float(val),
            observed_at=observed_at,
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


# league code -> does ESPN publish /teams for it. Populated by probing, never
# hand-authored: the set of leagues ESPN gives a team directory to is ESPN's
# business and changes without notice, so a literal list here would be a guess
# that rots. One probe per league per process, memoised because ENRICH runs its
# providers on a thread pool and would otherwise probe once per fixture.
_ESPN_TEAM_DIRECTORY: dict[str, bool] = {}
_ESPN_TEAM_DIRECTORY_LOCK = threading.Lock()


def _espn_league_has_team_directory(
    sport: str, league: str, rate_limiter: RateLimiter
) -> bool:
    """Whether ESPN answers ``/teams`` for this league.

    ESPN serves a team directory for its headline leagues and returns HTTP 404
    for the rest: verified live on 2026-08-25, ``esp.1`` returns 20 teams while
    ``sau.1`` and ``kor.1`` both 404, and ``/scoreboard`` answers 400 for them
    with and without a ``dates`` parameter. ``resolve_team_id`` swallows that
    404 and returns None, so the whole failure previously surfaced as "could not
    resolve team identity for 'Abha Club'" -- indistinguishable from a genuine
    name mismatch, and the reason every row of the 2026-08-25 sheet came back
    SINGLE_SOURCE off sportdb alone while ESPN sat on 10000 unspent requests.
    """
    with _ESPN_TEAM_DIRECTORY_LOCK:
        cached = _ESPN_TEAM_DIRECTORY.get(league)
    if cached is not None:
        return cached

    from bet.api_clients.espn import ESPNClient

    try:
        probe = ESPNClient(sport=sport, league=league, rate_limiter=rate_limiter)
        probe._request("/teams")
        supported = True
    except Exception:  # noqa: BLE001 - a 404 and a transport error are both "no directory"
        supported = False

    with _ESPN_TEAM_DIRECTORY_LOCK:
        _ESPN_TEAM_DIRECTORY[league] = supported
    return supported


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
        from bet.api_clients.espn import ESPNClient, get_espn_league_for_competition

        if not competition:
            raise ProviderLeagueUnsupported(
                "event carries no competition, cannot scope an ESPN league"
            )
        league = get_espn_league_for_competition(competition)
        if not league:
            raise ProviderLeagueUnsupported(
                f"no ESPN league code for competition '{competition}'"
            )
        if not _espn_league_has_team_directory("football", league, rate_limiter):
            raise ProviderLeagueUnsupported(
                f"ESPN publishes no team directory for league "
                f"'{league}' ('{competition}'), so no history can be fetched"
            )
        return ESPNClient(sport="football", league=league, rate_limiter=rate_limiter)
    if provider_key == "espn-tennis" and competition:
        from bet.api_clients.espn import ESPNClient, get_espn_league_for_competition

        league = get_espn_league_for_competition(competition)
        if league:
            return ESPNClient(sport="tennis", league=league, rate_limiter=rate_limiter)
    return get_client(provider_key, rate_limiter=rate_limiter)


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
        outcome.data_gaps.append(f"{provider_key}: could not resolve team identity for '{team_name}'")
        return outcome
    try:
        raw = getattr(client, method_name)(team_id, last_n=last_n)
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
        home_id = _field(fx, "home_participant_id", "home_team_id")
        home_team = _field(fx, "home_team")
        away_team = _field(fx, "away_team")
        if home_id is not None and str(home_id) == str(team_id):
            opponent = away_team
        elif str(home_team or "") == str(team_id):
            opponent = away_team
        else:
            opponent = home_team
        combined = _combine_stats(provider_key, stats_dict, aliases)
        for name, value in _make_values(
            provider_key, fixture_id, _field(fx, "date", default=""), str(opponent or "unknown"), combined
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
        for name, value in _make_values(
            provider_key, fixture_id, _field(meeting, "date", default=""), team_two, combined
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
        for name, value in _make_values(
            "understat", getattr(m, "fixture_id", ""), getattr(m, "date", ""), opponent, combined
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


def fetch_h2h_metrics(sport: str, team_one: str, team_two: str, rate_limiter: RateLimiter) -> FetchOutcome:
    """Fetch head-to-head metric observations between two teams/players,
    combining across every provider that supports name-based H2H lookup."""
    combined = FetchOutcome()
    for provider in PROVIDERS_BY_SPORT[sport]:
        if provider not in _H2H_SUPPORTED_PROVIDERS:
            combined.data_gaps.append(f"{provider}: h2h fetch not supported")
            continue
        combined.merge(_fetch_h2h_generic(provider, team_one, team_two, rate_limiter))
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

        opponent = away_name if home_id == str(team_id) else home_name
        match_date = str(match.get("date") or match.get("kickoff") or "")
        for name, value in _make_values(
            "highlightly", match_id, match_date, opponent or "unknown", combined
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
        anchor = datetime.now(timezone.utc).replace(tzinfo=None)
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
        if mode != "h2h":
            side = "home" if home_id == str(team_id) else "away" if away_id == str(team_id) else None
            if side is not None:
                combined.update(stats.get(side) or {})
        opponent = away.get("team_name") if home_id == str(team_id) else home.get("team_name")
        match_date = str(match.get("date") or match.get("kickoff") or "")
        for name, value in _make_values(
            "bzzoiro", match_id, match_date, opponent or "unknown", combined
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


# ------------------------------------------------------------- bzzoiro-tennis

# match_id -> ({canonical_total: value}, {"p1": {...}, "p2": {...}}, gap).
# Same reason the football cache exists: a historical match shows up in one
# player's form list, possibly the other's, and again in their H2H, and the
# tennis quota is 95 calls a *day*, so paying for it three times is not an
# inefficiency but a third of the budget.
_BZZOIRO_TENNIS_CACHE: dict[
    str, tuple[dict[str, float], dict[str, dict[str, float]], str | None]
] = {}
# match_id -> the listing payload from /matches/{id}/h2h/. One request serves
# team_a, team_b and h2h, and those three run as separate tasks on the thread
# pool, so without this they would each pay for it.
_BZZOIRO_TENNIS_LISTING_CACHE: dict[str, dict | None] = {}
# match_id -> the normalized header of a fetched box score, so a form-list row
# (which names only the opponent) can be told which side its player was on.
_BZZOIRO_TENNIS_HEADERS: dict[str, dict] = {}
_BZZOIRO_TENNIS_LOCK = threading.Lock()


def _bzzoiro_tennis_match_metrics(
    client: Any, match_id: str
) -> tuple[dict[str, float], dict[str, dict[str, float]], str | None]:
    """One historical match's canonical metrics: (totals, per-side, gap).

    Totals are both players summed, matching how STANDARD_MARKET_LINES phrases
    "Total Aces". Per-side is that player's own line, which tennis has always
    wanted -- ``first_serve_pct`` is a property of one server, not of a match --
    and which tennis-abstract already supplies for the player it was asked about.

    ``breaks_total`` is derived rather than read, and derived from *integers*
    rather than from the percentages next to them. A break of serve is a service
    game its server lost, so ``service_games - service_games_won`` per side, summed,
    is the number of breaks in the match. The payload also carries
    ``break_points_saved_pct`` / ``break_points_converted_pct``, but those are
    floats like 57.14285714285714, and recovering "4 of 7" from one means guessing
    a denominator -- a market priced off a reverse-engineered float is a fabricated
    market, so the count comes from the two integers that mean exactly what they say.
    """
    with _BZZOIRO_TENNIS_LOCK:
        cached = _BZZOIRO_TENNIS_CACHE.get(match_id)
    if cached is not None:
        return cached

    result = client.get_match_result(match_id)
    if result.status != SourceResultStatus.SUCCESS or not result.value:
        gap = (
            _BZZOIRO_NO_STATS
            if result.error_code == "statistics_empty"
            else f"bzzoiro-tennis: {getattr(result.status, 'value', result.status)}"
            f" for match {match_id}"
        )
        with _BZZOIRO_TENNIS_LOCK:
            _BZZOIRO_TENNIS_CACHE[match_id] = ({}, {}, gap)
        return {}, {}, gap

    sides_raw = result.value.get("sides") or {}
    sets_raw = result.value.get("sets") or {}
    header = result.value.get("match")

    # A retired or abandoned match can carry a partial box score -- aces and
    # service games up to the point somebody stopped -- which is a real number
    # describing a match that was not played. It reads as an unusually short
    # match and drags every UNDER line, so it is dropped here rather than
    # sampled. This is the first place the status is knowable: the form lists
    # these rows come from carry no status field.
    status = str((header or {}).get("match_status") or "").lower()
    if status and status not in BZZOIRO_TENNIS_FINISHED_STATUSES:
        with _BZZOIRO_TENNIS_LOCK:
            _BZZOIRO_TENNIS_CACHE[match_id] = ({}, {}, _BZZOIRO_NO_STATS)
        return {}, {}, _BZZOIRO_NO_STATS

    if isinstance(header, dict):
        # Kept so a form-list row -- which names only the opponent -- can be told
        # which side its player was on. The box score's own header is the only
        # place that says so.
        with _BZZOIRO_TENNIS_LOCK:
            _BZZOIRO_TENNIS_HEADERS[match_id] = header

    per_side: dict[str, dict[str, float]] = {}
    for side in ("p1", "p2"):
        stats = sides_raw.get(side) or {}
        per_side[side] = {
            canonical: float(stats[raw_name])
            for raw_name, canonical in _BZZOIRO_TENNIS_PLAYER_ALIASES.items()
            if stats.get(raw_name) is not None
        }

    totals: dict[str, float] = {}
    for raw_name, canonical in _BZZOIRO_TENNIS_TOTAL_ALIASES.items():
        one = (sides_raw.get("p1") or {}).get(raw_name)
        two = (sides_raw.get("p2") or {}).get(raw_name)
        # Both halves or neither: half a total is not a smaller total, it is the
        # wrong number, and it is the number an UNDER line would bank on.
        if one is None or two is None:
            continue
        totals[canonical] = float(one) + float(two)

    p1_sets, p2_sets = sets_raw.get("p1"), sets_raw.get("p2")
    if p1_sets is not None and p2_sets is not None:
        totals["total_sets"] = float(p1_sets) + float(p2_sets)

    breaks = 0.0
    saw_service_games = False
    for side in ("p1", "p2"):
        stats = sides_raw.get(side) or {}
        played, won = stats.get("service_games"), stats.get("service_games_won")
        if played is None or won is None or won > played:
            continue
        saw_service_games = True
        breaks += float(played) - float(won)
    if saw_service_games:
        totals["breaks_total"] = breaks

    with _BZZOIRO_TENNIS_LOCK:
        _BZZOIRO_TENNIS_CACHE[match_id] = (totals, per_side, None)
    return totals, per_side, None


def _bzzoiro_tennis_side_of(match_row: dict, player_id: str) -> str | None:
    """Which of ``p1``/``p2`` a player was in a historical match.

    A form-list row names only the *opponent*, so the player whose list it is
    cannot be read off it directly -- the box score's own header is what says
    which side they were.
    """
    one = (match_row.get("player_one") or {}).get("provider_player_id")
    two = (match_row.get("player_two") or {}).get("provider_player_id")
    if str(one or "") == str(player_id):
        return "p1"
    if str(two or "") == str(player_id):
        return "p2"
    return None


def _bzzoiro_tennis_is_before(match_date: str, as_of_date: str) -> bool:
    """Whether a form-list row predates the fixture being priced.

    Required, not defensive. ``/matches/{id}/h2h/`` returns each player's last
    five matches relative to **now**, not to the match: asked about fixture 44426
    (2026-08-01) it answered with matches from 2026-08-15 and 2026-08-17. Pricing
    a past date off that would put the result of the future in the evidence for
    the past, and would do it invisibly -- the numbers all look ordinary.

    A row with no date is kept: dropping it would discard a real observation over
    a formatting problem, and a future run's own date filter is applied
    server-side too.
    """
    day = (match_date or "")[:10]
    if not day or not as_of_date:
        return True
    return day < as_of_date[:10]


def fetch_bzzoiro_tennis_history(
    match_id: str,
    player_id: str,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None = None,
    last_n: int = 5,
    mode: str = "l10",
    as_of_date: str = "",
) -> FetchOutcome:
    """Historical canonical metrics from Bzzoiro's tennis product.

    ``mode="l10"`` reads one player's recent form; ``mode="h2h"`` reads the pair's
    meetings. Both are served by the **same single request** --
    ``/matches/{id}/h2h/`` returns ``player1_last5``, ``player2_last5`` and the
    meeting list together -- so the three enrichment slots cost one listing call
    between them rather than three. At 95 calls a day that is the difference
    between six enriched fixtures and two.

    ``match_id`` is this provider's id for the fixture being priced
    (``EventRecord.source_ids["bzzoiro-tennis"]``); ``player_id`` selects whose
    form to read in ``l10`` mode and is ignored for ``h2h``.

    In ``l10`` mode both families are emitted: the match totals (``aces_total``,
    ``double_faults_total``, ``total_games``, ``total_sets``, ``breaks_total``),
    so this provider corroborates espn-tennis where it can, and this player's own
    serve figures (``first_serve_pct`` and friends), which are the numbers tennis
    has always been missing -- espn-tennis aliases neither aces nor serve at all.

    In ``h2h`` mode only the totals are emitted: the slot carries no marker for
    which of the two a per-player value belongs to, so attributing one would mix
    the two players' samples where nobody could see it.
    """
    outcome = FetchOutcome()
    if not match_id:
        outcome.data_gaps.append("bzzoiro-tennis: missing native match id")
        return outcome
    if mode != "h2h" and not player_id:
        outcome.data_gaps.append("bzzoiro-tennis: missing native player id for l10")
        return outcome

    try:
        client = get_client("bzzoiro-tennis", rate_limiter=rate_limiter)
        listing = _bzzoiro_tennis_listing(
            client, str(match_id), run_budget, outcome.data_gaps
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure is a data_gap
        outcome.data_gaps.append(f"bzzoiro-tennis: {mode} error: {exc}")
        return outcome

    if listing is None:
        return outcome

    if mode == "h2h":
        rows = listing.get("h2h") or []
    else:
        side = next(
            (
                key
                for key in ("p1", "p2")
                if str(((listing.get("players") or {}).get(key) or {}).get(
                    "provider_player_id"
                ) or "") == str(player_id)
            ),
            None,
        )
        if side is None:
            outcome.data_gaps.append(
                f"bzzoiro-tennis: player {player_id} is not in match {match_id}"
            )
            return outcome
        rows = (listing.get("form") or {}).get(side) or []

    rows = [
        row
        for row in rows
        if row["provider_match_id"] != str(match_id)
        and _bzzoiro_tennis_is_before(str(row.get("date") or ""), as_of_date)
    ][:last_n]

    if not rows:
        outcome.data_gaps.append(
            f"bzzoiro-tennis: no {mode} history before {as_of_date or 'the fixture'}"
        )
        return outcome

    without_stats = 0
    for row in rows:
        historical_id = row["provider_match_id"]
        if run_budget is not None and not run_budget.try_consume("bzzoiro-tennis"):
            outcome.data_gaps.append("bzzoiro-tennis: run budget exhausted mid-history")
            break
        try:
            totals, per_side, gap = _bzzoiro_tennis_match_metrics(client, historical_id)
        except Exception as exc:  # noqa: BLE001
            outcome.data_gaps.append(
                f"bzzoiro-tennis: match {historical_id} stats error: {exc}"
            )
            continue
        if gap == _BZZOIRO_NO_STATS:
            # A walkover or retirement: the row exists, the box score does not.
            without_stats += 1
            continue
        if gap:
            outcome.data_gaps.append(gap)
            continue

        combined = dict(totals)
        if mode != "h2h":
            with _BZZOIRO_TENNIS_LOCK:
                header = _BZZOIRO_TENNIS_HEADERS.get(historical_id)
            historical_side = (
                _bzzoiro_tennis_side_of(header, str(player_id)) if header else None
            )
            if historical_side is not None:
                combined.update(per_side.get(historical_side) or {})

        opponent = (row.get("opponent") or {}).get("player_name")
        for name, value in _make_values(
            "bzzoiro-tennis",
            historical_id,
            str(row.get("date") or ""),
            opponent or "unknown",
            combined,
        ).items():
            outcome.add(name, value)

    if without_stats:
        outcome.data_gaps.append(
            f"bzzoiro-tennis: {without_stats} of {len(rows)} {mode} matches were "
            f"walkovers or carry no box score"
        )
    return outcome



def _bzzoiro_tennis_listing(
    client: Any, match_id: str, run_budget: RunBudget | None, gaps: list[str]
) -> dict | None:
    with _BZZOIRO_TENNIS_LOCK:
        if match_id in _BZZOIRO_TENNIS_LISTING_CACHE:
            return _BZZOIRO_TENNIS_LISTING_CACHE[match_id]

    if run_budget is not None and not run_budget.try_consume("bzzoiro-tennis"):
        gaps.append("bzzoiro-tennis: run budget exhausted before listing")
        return None

    result = client.get_h2h_result(match_id)
    if result.status not in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
        status_label = getattr(result.status, "value", str(result.status))
        gaps.append(f"bzzoiro-tennis: {status_label} listing for match {match_id}")
        with _BZZOIRO_TENNIS_LOCK:
            _BZZOIRO_TENNIS_LISTING_CACHE[match_id] = None
        return None

    value = result.value or {}
    with _BZZOIRO_TENNIS_LOCK:
        _BZZOIRO_TENNIS_LISTING_CACHE[match_id] = value
    return value


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
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - parsed).days
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
