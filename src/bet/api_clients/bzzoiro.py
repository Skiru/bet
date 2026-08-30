"""Bzzoiro Sports Data client (``sports.bzzoiro.com/api/v2``).

Why this provider exists in the roster at all: the pipeline's binding constraint
was never the fixtures, it was Highlightly's 100-calls-a-day cap, which on
2026-08-25 left 175 of 181 events BLOCKED. Bzzoiro removes that constraint --
on the PRO plan this product sends no rate-limit header at all (verified live
2026-08-28 across /leagues/, /events/, /events/{id}/stats/ and /coverage/;
the free plan had answered ``ratelimit-policy: "football";q=7500;w=86400``) --
and serves three things Highlightly does not:

* ``/events/{id}/stats/`` returns **home and away separately**, so a per-team
  total is a real observation rather than a match total halved;
* ``/players/{id}/stats/`` returns a player's per-match history *inline*, so a
  player prop costs one call rather than one-plus-N;
* Champions/Europa/Conference League are first-class leagues with their own ids,
  which is where the winning coupons actually came from.

Two shapes of this API drive decisions below and are easy to get wrong:

1. **Listings page ascending and ignore ``ordering``.** ``?ordering=-event_date``
   is silently accepted and has no effect (verified live). So "this team's last
   ten matches" cannot be read off page one -- page one is the *oldest* ten. The
   listing methods therefore take explicit ``limit``/``offset`` and report
   ``total_count``, and the caller pages to the end. Sorting a truncated first
   page descending would have produced a "last ten" from 2024.
2. **``/players/{id}/stats/`` rows carry no date and no opponent**, only
   ``event_id``. They are ordered newest-first (unlike the listings), which is
   what makes ``limit=N`` correct there. Attaching a date is the caller's job,
   from the team-fixtures history it already holds.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from bet.integration.evidence import namespaced_source_refs
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

from .base_client import BaseAPIClient
from .env import get_env
from .evidence_request import EvidenceRequestMixin
from .rate_limiter import RateLimiter

LEAGUES_PARSER_VERSION = "bzzoiro-leagues-v1"
EVENTS_PARSER_VERSION = "bzzoiro-events-v1"
EVENT_PARSER_VERSION = "bzzoiro-event-v1"
TEAM_FIXTURES_PARSER_VERSION = "bzzoiro-team-fixtures-v1"
STATISTICS_PARSER_VERSION = "bzzoiro-statistics-v1"
PLAYER_STATS_PARSER_VERSION = "bzzoiro-player-stats-v1"
LINEUPS_PARSER_VERSION = "bzzoiro-lineups-v1"
ODDS_PARSER_VERSION = "bzzoiro-odds-v1"
CONSENSUS_ODDS_PARSER_VERSION = "bzzoiro-consensus-odds-v1"
ODDS_COMPARISON_PARSER_VERSION = "bzzoiro-odds-comparison-v1"
PREDICTION_PARSER_VERSION = "bzzoiro-prediction-v1"
REFEREE_PARSER_VERSION = "bzzoiro-referee-v1"
TEAM_SQUAD_PARSER_VERSION = "bzzoiro-team-squad-v1"
STANDINGS_PARSER_VERSION = "bzzoiro-standings-v1"
EVENT_PLAYER_STATS_PARSER_VERSION = "bzzoiro-event-player-stats-v1"

# ``availability`` values that mean the player cannot be picked. The provider
# also emits "available", and an empty string on players it has no report for --
# neither is an absence, and treating "" as one would invent injuries for every
# squad the provider covers thinly.
UNAVAILABLE_STATUSES = frozenset({"injured", "suspended", "doubtful"})

# Raw ``market`` code -> canonical code, and the same for ``outcome``.
#
# The values are identical to the keys because this provider's codes are already
# the canonical ones. The map exists anyway, and is not replaced by a frozenset,
# for the same reason STAT_NAME_MAP is a map: it is the single place a raw code
# is *filtered*, so a market the provider adds tomorrow lands in
# ``unknown_markets`` as a diagnostic rather than reaching a Literal-typed
# contract field and raising a ValidationError mid-run.
#
# Contrast PROVIDER_NAMES, which is a closed Literal validated against directly:
# a provider name is a human's config-time decision, so an unlisted one is a
# mistake worth failing on. A market code belongs to the live API.
MARKET_NAME_MAP: dict[str, str] = {
    "1x2": "1x2",
    "btts": "btts",
    "over_under_05": "over_under_05",
    "over_under_15": "over_under_15",
    "over_under_25": "over_under_25",
    "over_under_35": "over_under_35",
    "double_chance": "double_chance",
    "draw_no_bet": "draw_no_bet",
    "european_handicap": "european_handicap",
    "asian_handicap": "asian_handicap",
    "total_corners": "total_corners",
    "corners_1x2": "corners_1x2",
    "total_red_cards": "total_red_cards",
    "red_card": "red_card",
    "match_winner": "match_winner",
}

OUTCOME_NAME_MAP: dict[str, str] = {
    "HOME": "HOME",
    "DRAW": "DRAW",
    "AWAY": "AWAY",
    "over": "over",
    "under": "under",
    "yes": "yes",
    "no": "no",
    "1X": "1X",
    "12": "12",
    "X2": "X2",
}

# ``/events/{id}/odds/`` answers a flat block of named prices rather than the
# (market, outcome, line) tuples ``/odds/`` returns, so its keys are carried
# through verbatim into ``consensus_odds``. Surveyed live 2026-08-28: the block
# holds 1x2, goals over/under and BTTS, and **no corners market of any kind** --
# which is why the corners signal is never sourced from here.
CONSENSUS_ODDS_KEYS = frozenset(
    {
        "home_win",
        "draw",
        "away_win",
        "over_15_goals",
        "over_25_goals",
        "over_35_goals",
        "under_15_goals",
        "under_25_goals",
        "under_35_goals",
        "btts_yes",
        "btts_no",
    }
)

# The model serves probabilities 0-100; every consumer compares them against a
# 1/decimal_odds figure, which the same API serves 0-1. Converted once, here.
_PERCENT_TO_FRACTION = 100.0

# Raw ``stats.home`` / ``stats.away`` key -> (normalized name, unit).
# Deliberately partial: the payload carries ~50 keys per side (ball carries,
# normalized value models, phase-of-play splits) and this pipeline analyses
# count markets. Unmapped keys are reported in ``unknown_metrics`` rather than
# dropped silently, so a renamed field surfaces as a diagnostic.
STAT_NAME_MAP: dict[str, tuple[str, str]] = {
    "corner_kicks": ("corners", "count"),
    "yellow_cards": ("yellow_cards", "count"),
    "red_cards": ("red_cards", "count"),
    "total_shots": ("shots", "count"),
    "shots_on_target": ("shots_on_target", "count"),
    "shots_off_target": ("shots_off_target", "count"),
    "blocked_shots": ("blocked_shots", "count"),
    "fouls": ("fouls", "count"),
    "offsides": ("offsides", "count"),
    "ball_possession": ("possession", "ratio"),
}

# Per-match player fields this pipeline can price. ``was_fouled`` is kept
# alongside ``fouls`` because they are opposite sides of the same market and a
# provider that reports only one of them cannot serve "fouls committed" props.
PLAYER_STAT_MAP: dict[str, tuple[str, str]] = {
    "total_shots": ("player_total_shots", "count"),
    "shots_on_target": ("player_shots_on_target", "count"),
    "fouls": ("player_fouls", "count"),
    "was_fouled": ("player_was_fouled", "count"),
    "yellow_card": ("player_yellow_cards", "count"),
    "red_card": ("player_red_cards", "count"),
}

# ``status`` values that mean the match was played to a result, so
# ``/events/{id}/stats/`` has something to return. Surveyed live over a
# four-week window: the only other values are ``notstarted`` and ``postponed``.
FINISHED_STATUSES = frozenset({"finished", "ft", "aet", "pen"})

# ``limit`` is capped server-side: a request for 500 answered with 200 rows.
MAX_PAGE_SIZE = 200


def extract_quota_metadata(
    headers: dict[str, Any] | None,
) -> dict[str, int | str | None]:
    """Daily quota from Bzzoiro's RFC-draft rate-limit headers.

        ratelimit:        "tennis";r=85;t=56393
        ratelimit-policy: "tennis";q=100;w=86400

    ``r`` is requests remaining, ``t`` seconds until the window resets, ``q`` the
    quota and ``w`` the window in seconds. Read rather than assumed because this
    is the one provider whose real ceiling the pipeline can see, and ``preflight``
    reports it back to the operator.

    ``{}`` when the headers are absent, which is not a parse failure but the
    answer: on the PRO plan the *football* product stops sending them entirely
    while tennis keeps reporting 100 a day on the same account and the same key.
    Reporting nothing is what lets the football product read as unlimited instead
    of inheriting a number from its sibling.

    Shared with the tennis client (``bzzoiro_tennis.py``): the header syntax is
    identical and only the policy *name* differs. The name is deliberately not
    parsed -- the bucket a response describes is the bucket the request went to.
    """
    if not headers:
        return {}
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    metadata: dict[str, int | str | None] = {}
    field_map = {
        ("ratelimit", "r"): "daily_remaining",
        ("ratelimit", "t"): "reset_seconds",
        ("ratelimit-policy", "q"): "daily_limit",
        ("ratelimit-policy", "w"): "window_seconds",
    }
    for (header_name, key), field_name in field_map.items():
        raw = normalized.get(header_name)
        if raw is None:
            continue
        match = re.search(rf"(?:^|[;,\s]){re.escape(key)}=(\d+)", raw)
        if match is None:
            continue
        metadata[field_name] = int(match.group(1))
    return metadata


class BzzoiroClient(EvidenceRequestMixin, BaseAPIClient):
    """Football-only client for Bzzoiro's v2 REST API."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="bzzoiro",
            base_url="https://sports.bzzoiro.com/api/v2",
            rate_limiter=rate_limiter,
        )

    def _load_api_key(self) -> str | None:
        # BZZORIO_KEY, not BZZOIRO_KEY: that is the spelling the provider's own
        # dashboard issues and the one already in .env / .env.example. The
        # provider *name* keeps the site's spelling (bzzoiro), so the quota
        # override derived from it is BET_LIMIT_BZZOIRO -- the two differ, which
        # is why both are spelled out here instead of being derived.
        return get_env("BZZORIO_KEY") or super()._load_api_key()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Token {self.api_key}"
        return headers

    @staticmethod
    def _extract_quota_metadata(
        headers: dict[str, Any] | None,
    ) -> dict[str, int | str | None]:
        return extract_quota_metadata(headers)

    @staticmethod
    def _classify_provider_payload_error(
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Bzzoiro answers ``{"error": true, "status": 404, "detail": "Not found"}``
        with the matching HTTP status, so the transport branches already cover it.
        Only a 200 carrying ``error`` needs handling here."""
        if not payload.get("error"):
            return None
        detail = str(payload.get("detail") or "").lower()
        if "limit" in detail or "throttl" in detail:
            return {
                "status": SourceResultStatus.RATE_LIMITED,
                "error_code": "provider_rate_limited",
            }
        return {
            "status": SourceResultStatus.UPSTREAM_ERROR,
            "error_code": "provider_error_payload",
        }

    # BaseAPIClient's abstract surface. Bzzoiro is reached through the *_result
    # methods below; these exist so the class is instantiable and so nothing
    # silently receives a half-typed legacy shape.
    def get_fixtures(self, date: str) -> list:
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Not served by a two-team endpoint, and deliberately not faked with one.

        Bzzoiro embeds the pair's meeting history in the fixture itself, under
        ``head_to_head.recent_matches`` (see ``get_event_result``), so H2H costs
        no listing call at all. Synthesising it from two ``/teams`` histories
        here would spend two calls to reconstruct something already in hand.
        """
        return []

    # ----------------------------------------------------------------- leagues

    def get_leagues_result(
        self, *, limit: int = MAX_PAGE_SIZE
    ) -> SourceOperationResult[dict[str, Any]]:
        """The whole league catalogue in one request (83 rows as of 2026-08-28).

        Needed because ``/events/`` names a fixture's competition only by
        ``league_id``, and ``EventRecord.competition`` is part of the event id and
        of every downstream competition lookup. One call per run resolves all of
        them, so this is cheaper than it looks.
        """
        result = self._request_with_evidence(
            endpoint="/leagues/",
            params={"limit": min(int(limit), MAX_PAGE_SIZE)},
            operation="league_discovery",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("results")
        if not isinstance(rows, list):
            return self._schema_error(result, "results_not_list")

        leagues = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            league_id = str(row.get("id") or "").strip()
            name = str(row.get("name") or "").strip()
            if not league_id or not name:
                continue
            leagues.append(
                {
                    "provider_league_id": league_id,
                    "league_name": name,
                    "country_name": row.get("country"),
                    "is_women": bool(row.get("is_women")),
                    "is_active": bool(row.get("is_active")),
                }
            )

        return self._bundle_result(
            result=result,
            parser_version=LEAGUES_PARSER_VERSION,
            operation_name="league_discovery",
            source_event_refs=[],
            value={"leagues": leagues, "accepted_count": len(leagues)},
            parser_diagnostics={"raw_count": len(rows), "accepted_count": len(leagues)},
            forced_status=None if leagues else SourceResultStatus.VALID_EMPTY,
        )

    # ------------------------------------------------------------------ events

    def get_event_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """One fixture, plus the pair's meeting history embedded in it.

        ``head_to_head.recent_matches`` carries each past meeting's ``event_id``,
        date, both team ids and both names -- everything the H2H slot needs to go
        straight to ``/events/{id}/stats/``, without a listing call.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/",
            params={},
            operation="historical_form_h2h",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")

        event = _normalize_event_row(payload, requested_team_id=None, source_order=1)
        if event is None:
            return self._schema_error(result, "event_row_unusable")

        h2h_raw = payload.get("head_to_head")
        h2h_raw = h2h_raw if isinstance(h2h_raw, dict) else {}
        h2h_matches = []
        for index, row in enumerate(h2h_raw.get("recent_matches") or [], start=1):
            if not isinstance(row, dict):
                continue
            # The listing includes *this* fixture. Keeping it would let the match
            # being priced into its own evidence sample.
            if str(row.get("event_id") or "") == str(event_id):
                continue
            normalized = _normalize_event_row(
                {
                    "id": row.get("event_id"),
                    "home_team_id": row.get("home_team_id"),
                    "away_team_id": row.get("away_team_id"),
                    "home_team": row.get("home"),
                    "away_team": row.get("away"),
                    "home_score": row.get("home_score"),
                    "away_score": row.get("away_score"),
                    "event_date": row.get("date"),
                    # A meeting listed with a final score was played; the H2H
                    # block carries no status field of its own.
                    "status": "finished" if row.get("score") else None,
                    "league_id": None,
                },
                requested_team_id=None,
                source_order=index,
            )
            if normalized is not None:
                h2h_matches.append(normalized)

        return self._bundle_result(
            result=result,
            parser_version=EVENT_PARSER_VERSION,
            operation_name="historical_form_h2h",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "event": event,
                "matches": h2h_matches,
                "accepted_count": len(h2h_matches),
                "h2h_summary": {
                    key: h2h_raw.get(key)
                    for key in ("total_matches", "home_wins", "draws", "away_wins")
                },
            },
            parser_diagnostics={"accepted_count": len(h2h_matches)},
            forced_status=None if h2h_matches else SourceResultStatus.VALID_EMPTY,
        )

    def get_events_result(
        self,
        *,
        date_from: str,
        date_to: str,
        league_id: str | int | None = None,
        team_id: str | int | None = None,
        status: str | None = None,
        limit: int = MAX_PAGE_SIZE,
        offset: int = 0,
    ) -> SourceOperationResult[dict[str, Any]]:
        """One page of ``/events/``, normalized. ``total_count`` is the unpaged
        total, which is how a caller reaches the newest rows of an ascending
        listing."""
        params: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "limit": min(int(limit), MAX_PAGE_SIZE),
            "offset": int(offset),
        }
        if league_id is not None:
            params["league"] = str(league_id)
        if team_id is not None:
            params["team"] = str(team_id)
        if status is not None:
            params["status"] = status
        return self._listing_result(
            endpoint="/events/",
            params=params,
            operation="match_discovery",
            parser_version=EVENTS_PARSER_VERSION,
            requested_team_id=str(team_id) if team_id is not None else None,
        )

    def get_team_fixtures_result(
        self,
        team_id: str | int,
        *,
        date_from: str,
        date_to: str,
        limit: int = 10,
        offset: int = 0,
        status: str | None = "finished",
    ) -> SourceOperationResult[dict[str, Any]]:
        """One page of ``/teams/{id}/fixtures/``, oldest first.

        ``date_from`` is required by the caller, not optional: without it the
        endpoint reaches back to rows stamped 1970 (verified live), and with no
        ``date_to`` at all it returns only *upcoming* fixtures -- one row for a
        team mid-season, which reads exactly like a provider with no history.
        """
        params: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "limit": min(int(limit), MAX_PAGE_SIZE),
            "offset": int(offset),
        }
        if status is not None:
            params["status"] = status
        return self._listing_result(
            endpoint=f"/teams/{team_id}/fixtures/",
            params=params,
            operation="current_form",
            parser_version=TEAM_FIXTURES_PARSER_VERSION,
            requested_team_id=str(team_id),
        )

    def _listing_result(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        operation: str,
        parser_version: str,
        requested_team_id: str | None,
    ) -> SourceOperationResult[dict[str, Any]]:
        result = self._request_with_evidence(
            endpoint=endpoint, params=params, operation=operation
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("results")
        if not isinstance(rows, list):
            return self._schema_error(result, "results_not_list")

        matches = []
        rejected_count = 0
        for index, row in enumerate(rows, start=1):
            normalized = _normalize_event_row(
                row, requested_team_id=requested_team_id, source_order=index
            )
            if normalized is None:
                rejected_count += 1
                continue
            matches.append(normalized)

        total_count = payload.get("count")
        return self._bundle_result(
            result=result,
            parser_version=parser_version,
            operation_name=operation,
            source_event_refs=namespaced_source_refs(
                self.api_name, [item["provider_match_id"] for item in matches]
            ),
            value={
                "provider_team_id": requested_team_id,
                "total_count": int(total_count)
                if isinstance(total_count, int)
                else len(matches),
                "offset": int(params.get("offset") or 0),
                "accepted_count": len(matches),
                "rejected_count": rejected_count,
                "matches": matches,
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(matches),
                "rejected_count": rejected_count,
            },
            forced_status=None if matches else SourceResultStatus.VALID_EMPTY,
        )

    # -------------------------------------------------------------- statistics

    def get_statistics_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """``/events/{id}/stats/`` with the home/away split **preserved**.

        Every other provider in this pipeline collapses a match to one combined
        total in its client, which is why no per-team market could be priced from
        any of them. Summing is a decision, and it is made in
        ``simple_stats/providers.py`` where both readings are wanted at once:
        ``corners_total`` for the match market and ``corners_for`` for the team
        one. Collapsing here would throw away the reason this provider was added.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/stats/",
            params={},
            operation="detailed_metrics",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        stats = payload.get("stats")
        if not isinstance(stats, dict):
            return self._schema_error(result, "stats_not_object")

        stats_rows: list[dict[str, Any]] = []
        raw_stat_field_names: list[str] = []
        raw_stat_name_set: set[str] = set()
        unknown_metrics: list[str] = []
        rejected_count = 0

        for side in ("home", "away"):
            # first_half / second_half live alongside home/away in the same
            # object; only the full-match figures are read, matching how
            # STANDARD_MARKET_LINES phrases its markets.
            side_stats = stats.get(side)
            if not isinstance(side_stats, dict):
                rejected_count += 1
                continue
            for raw_name, raw_value in side_stats.items():
                if raw_name not in raw_stat_name_set:
                    raw_stat_name_set.add(raw_name)
                    raw_stat_field_names.append(raw_name)
                mapping = STAT_NAME_MAP.get(raw_name)
                if mapping is None:
                    if raw_name not in unknown_metrics:
                        unknown_metrics.append(raw_name)
                    continue
                value = _scalar(raw_value)
                if value is None:
                    # Includes ``"red_cards": null`` on a match with no red
                    # card. Absent is not zero: a null recorded as 0 would let
                    # an UNDER line bank an observation the provider never made.
                    rejected_count += 1
                    continue
                stats_rows.append(
                    {
                        "provider_match_id": str(event_id),
                        "side": side,
                        "raw_stat_name": raw_name,
                        "normalized_metric_name": mapping[0],
                        "value": value,
                        "unit": mapping[1],
                        "parser_version": STATISTICS_PARSER_VERSION,
                    }
                )

        if not stats_rows:
            return self._schema_error(result, "statistics_empty")

        return self._bundle_result(
            result=result,
            parser_version=STATISTICS_PARSER_VERSION,
            operation_name="detailed_metrics",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "statistics": stats_rows,
                "raw_stat_field_names": raw_stat_field_names,
                "normalized_metric_names": [
                    row["normalized_metric_name"] for row in stats_rows
                ],
                "accepted_count": len(stats_rows),
                "rejected_count": rejected_count,
                "unknown_metrics": unknown_metrics,
            },
            parser_diagnostics={
                "accepted_count": len(stats_rows),
                "rejected_count": rejected_count,
                "raw_stat_fields_count": len(raw_stat_field_names),
                "unknown_metrics": unknown_metrics,
            },
        )

    # ------------------------------------------------------------ player props

    def get_player_stats_result(
        self,
        player_id: str | int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 10,
    ) -> SourceOperationResult[dict[str, Any]]:
        """A player's per-match box scores, **newest first**, in one request.

        This listing is ordered the opposite way from ``/events/`` and
        ``/teams/{id}/fixtures/`` (verified live: row one is the player's most
        recent appearance), which is the only reason ``limit=N`` gives the last N
        here without paging to the end.

        Rows carry ``event_id`` but no date and no opponent, so each is returned
        with ``match_date``/``opponent`` unset for the caller to fill from the
        team history it already fetched.

        Both ``date_from`` and ``date_to`` are honoured server-side (verified
        live). ``date_to`` matters for a backfill: without it the fixture being
        priced is in its own evidence sample.
        """
        params: dict[str, Any] = {"limit": min(int(limit), MAX_PAGE_SIZE)}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        result = self._request_with_evidence(
            endpoint=f"/players/{player_id}/stats/",
            params=params,
            operation="player_form",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("results")
        if not isinstance(rows, list):
            return self._schema_error(result, "results_not_list")

        appearances = []
        rejected_count = 0
        for row in rows:
            if not isinstance(row, dict):
                rejected_count += 1
                continue
            event_id = str(row.get("event_id") or "").strip()
            if not event_id:
                rejected_count += 1
                continue
            metrics: dict[str, float] = {}
            for raw_name, (normalized_name, _unit) in PLAYER_STAT_MAP.items():
                value = _scalar(row.get(raw_name))
                if value is not None:
                    metrics[normalized_name] = value
            appearances.append(
                {
                    "provider_match_id": event_id,
                    "provider_team_id": str(row.get("team_id") or ""),
                    "minutes_played": _scalar(row.get("minutes_played")) or 0.0,
                    "rating": _scalar(row.get("rating")),
                    "metrics": metrics,
                }
            )

        total_count = payload.get("count")
        return self._bundle_result(
            result=result,
            parser_version=PLAYER_STATS_PARSER_VERSION,
            operation_name="player_form",
            source_event_refs=namespaced_source_refs(
                self.api_name, [item["provider_match_id"] for item in appearances]
            ),
            value={
                "provider_player_id": str(player_id),
                "total_count": int(total_count)
                if isinstance(total_count, int)
                else len(appearances),
                "accepted_count": len(appearances),
                "rejected_count": rejected_count,
                "appearances": appearances,
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(appearances),
                "rejected_count": rejected_count,
            },
            forced_status=None if appearances else SourceResultStatus.VALID_EMPTY,
        )

    def get_lineups_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """``/events/{id}/lineups/`` -- who to ask about, and how sure we are.

        One endpoint serves both cases: ``lineup_status`` is ``"confirmed"`` once
        the teams announce, and ``"predicted"`` before that (with ``beta: true``,
        a per-team ``confidence`` and a per-player ``ai_score``). The separate
        ``/predicted-lineup/{id}/`` path in the API docs answers 404 and is not
        used.

        The status travels with the value rather than being resolved here,
        because a prop off a predicted XI is a weaker claim than one off a
        confirmed XI and the artifact has to say which it is.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/lineups/",
            params={},
            operation="lineups",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        lineups = payload.get("lineups")
        if not isinstance(lineups, dict):
            return self._schema_error(result, "lineups_not_object")

        lineup_status = str(payload.get("lineup_status") or "").lower()
        sides: dict[str, dict[str, Any]] = {}
        for side in ("home", "away"):
            block = lineups.get(side)
            if not isinstance(block, dict):
                continue
            players = []
            for entry in block.get("players") or []:
                if not isinstance(entry, dict):
                    continue
                player_id = str(entry.get("id") or "").strip()
                name = str(entry.get("name") or "").strip()
                if not player_id or not name:
                    continue
                players.append(
                    {
                        "player_id": player_id,
                        "player_name": name,
                        "position": entry.get("position"),
                        "captain": bool(entry.get("captain")),
                        "ai_score": _scalar(entry.get("ai_score")),
                    }
                )
            sides[side] = {
                "provider_team_id": str(block.get("team_id") or ""),
                "team_name": block.get("team_name"),
                "formation": block.get("formation"),
                "confidence": _scalar(block.get("confidence")),
                # Starters only. A substitute's minutes are decided during the
                # match, so his last-ten is a sample of a different thing than
                # the prop being priced.
                "players": players,
            }

        if not any(side.get("players") for side in sides.values()):
            return self._schema_error(result, "lineups_empty")

        return self._bundle_result(
            result=result,
            parser_version=LINEUPS_PARSER_VERSION,
            operation_name="lineups",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "lineup_status": lineup_status,
                "sides": sides,
            },
            parser_diagnostics={
                "lineup_status": lineup_status,
                "home_players": len(sides.get("home", {}).get("players") or []),
                "away_players": len(sides.get("away", {}).get("players") or []),
            },
        )


    # -------------------------------------------------- odds and predictions
    #
    # Everything below is a *point-in-time snapshot*, not a sample. Nothing here
    # ever produces a ``ProviderValue``: those are observations of played
    # matches and carry a match id and a date you can go and check. A price is
    # what a bookmaker currently thinks, and a prediction is what a model
    # currently thinks. Coercing either into the sample arithmetic upstream --
    # the obvious way to reuse the Wilson bound already written -- would put a
    # number with no matches behind it into a figure whose whole value is that
    # you can ask which matches it came from.

    def get_odds_result(
        self,
        event_id: str | int,
        *,
        market: str | None = None,
        limit: int = MAX_PAGE_SIZE,
    ) -> SourceOperationResult[dict[str, Any]]:
        """Every tracked bookmaker's quotes for one event, from ``/odds/``.

        This is the corners price path, and it is deliberately *not*
        ``/events/{id}/odds/`` or ``/odds/best/``, both of which look like the
        obvious choice and cannot do the job (verified live 2026-08-28):

        * ``/events/{id}/odds/`` returns a consensus block covering 1x2, goals
          over/under and BTTS, with **no corners market at all**;
        * ``/odds/best/`` is scoped by date range and league, not by event -- one
          response carried 313 unrelated fixtures -- so reaching one event's
          corners through it means paging a day's slate to find it.

        ``is_best`` is therefore computed here rather than read from the
        provider's own ``is_max_quote`` flag: filtering an event's corners
        quotes by ``is_max_quote=true`` returned zero rows against an event that
        demonstrably had twelve, so the flag is not maintained on this feed and
        trusting it would report no best price rather than the wrong one.
        """
        params: dict[str, Any] = {
            "event_id": int(event_id),
            "limit": min(int(limit), MAX_PAGE_SIZE),
        }
        if market is not None:
            params["market"] = market
        result = self._request_with_evidence(
            endpoint="/odds/",
            params=params,
            operation="market_odds",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("results")
        if not isinstance(rows, list):
            return self._schema_error(result, "results_not_list")

        quotes: list[dict[str, Any]] = []
        unknown_markets: list[str] = []
        rejected_count = 0
        unlinked_count = 0

        for row in rows:
            if not isinstance(row, dict):
                rejected_count += 1
                continue
            # ``event_id`` is documented nullable: a quote the provider could not
            # link to a fixture in its own catalogue. Attaching one of those to
            # the event we happened to be asking about would invent a price for a
            # match it was never quoted on.
            row_event_id = row.get("event_id")
            if row_event_id is None or str(row_event_id) != str(event_id):
                unlinked_count += 1
                continue
            raw_market = str(row.get("market") or "")
            canonical_market = MARKET_NAME_MAP.get(raw_market)
            if canonical_market is None:
                if raw_market and raw_market not in unknown_markets:
                    unknown_markets.append(raw_market)
                continue
            canonical_outcome = OUTCOME_NAME_MAP.get(str(row.get("outcome") or ""))
            if canonical_outcome is None:
                rejected_count += 1
                continue
            price = _scalar(row.get("decimal_odds"))
            if price is None or price <= 0:
                rejected_count += 1
                continue
            quotes.append(
                {
                    "market": canonical_market,
                    "outcome": canonical_outcome,
                    "line": _scalar(row.get("line")),
                    "price": price,
                    "implied_probability": _scalar(row.get("implied_probability")),
                    "bookmaker_slug": str(row.get("bookmaker_slug") or "") or None,
                    "bookmaker_name": str(row.get("bookmaker_name") or "") or None,
                    "is_best": False,
                    "updated_at": str(row.get("updated_at") or "") or None,
                }
            )

        _mark_best_quotes(quotes)

        return self._bundle_result(
            result=result,
            parser_version=ODDS_PARSER_VERSION,
            operation_name="market_odds",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "quotes": quotes,
                "accepted_count": len(quotes),
                "rejected_count": rejected_count,
                "unlinked_count": unlinked_count,
                "unknown_markets": unknown_markets,
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(quotes),
                "rejected_count": rejected_count,
                "unlinked_count": unlinked_count,
                "unknown_markets": unknown_markets,
            },
            forced_status=None if quotes else SourceResultStatus.VALID_EMPTY,
        )

    def get_consensus_odds_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """``/events/{id}/odds/`` -- the provider's own consensus block.

        Context only. It covers 1x2, goals over/under and BTTS, none of which
        this pipeline currently prices, and it carries no corners market, which
        is the one it does. Collected because it costs one call on an uncapped
        product and is the natural price source on the day goals/BTTS are
        unlocked; read by nothing that can promote a row today.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/odds/",
            params={},
            operation="consensus_odds",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        odds = payload.get("odds")
        if not isinstance(odds, dict):
            return self._schema_error(result, "odds_not_object")

        prices: dict[str, float] = {}
        unknown_keys: list[str] = []
        for key, raw_value in odds.items():
            if key not in CONSENSUS_ODDS_KEYS:
                unknown_keys.append(str(key))
                continue
            value = _scalar(raw_value)
            if value is not None and value > 0:
                prices[str(key)] = value

        return self._bundle_result(
            result=result,
            parser_version=CONSENSUS_ODDS_PARSER_VERSION,
            operation_name="consensus_odds",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "consensus_odds": prices,
                "last_update_at": payload.get("last_update_at"),
                "unknown_keys": unknown_keys,
            },
            parser_diagnostics={
                "accepted_count": len(prices),
                "unknown_keys": unknown_keys,
            },
            forced_status=None if prices else SourceResultStatus.VALID_EMPTY,
        )

    def get_odds_comparison_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """The full per-bookmaker grid -- or the recorded fact that we cannot see it.

        ``/odds/comparison/`` requires the "Football Unlimited" entitlement and
        answers 403 ``bookmakers_not_entitled`` without it. That 403 is a
        **successful, informative** answer: it says something true and stable
        about the account, it will not resolve on a retry, and it is not a gap in
        the provider's data. Returning it as an error would put a permanent
        billing state into every event's ``data_gaps`` and would make the
        retry-eligible failures around it unreadable.

        ``EvidenceRequestMixin`` turns a 403 into ``BLOCKED``/``http_status=403``
        before any payload-parsing runs, so that is what is caught here.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/odds/comparison/",
            params={},
            operation="odds_comparison",
            source_event_id=str(event_id),
        )
        if result.status is SourceResultStatus.BLOCKED and result.http_status == 403:
            return self._bundle_result(
                result=result,
                parser_version=ODDS_COMPARISON_PARSER_VERSION,
                operation_name="odds_comparison",
                source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
                value={
                    "provider_match_id": str(event_id),
                    "entitlement": "NOT_ENTITLED",
                    "quotes": [],
                    "bookmakers_count": 0,
                    "unknown_markets": [],
                },
                parser_diagnostics={"entitlement": "NOT_ENTITLED", "http_status": 403},
                forced_status=SourceResultStatus.SUCCESS,
            )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        markets = payload.get("markets")
        if not isinstance(markets, dict):
            return self._schema_error(result, "markets_not_object")

        quotes: list[dict[str, Any]] = []
        unknown_markets: list[str] = []
        for raw_market, selections in markets.items():
            canonical_market = MARKET_NAME_MAP.get(str(raw_market))
            if canonical_market is None:
                if str(raw_market) not in unknown_markets:
                    unknown_markets.append(str(raw_market))
                continue
            if not isinstance(selections, dict):
                continue
            for selection in selections.values():
                if not isinstance(selection, dict):
                    continue
                canonical_outcome = OUTCOME_NAME_MAP.get(str(selection.get("outcome") or ""))
                if canonical_outcome is None:
                    continue
                line = _scalar(selection.get("line"))
                best_slug = str(selection.get("best_bookmaker_slug") or "") or None
                best_name = str(selection.get("best_bookmaker_name") or "") or None
                books = selection.get("bookmakers")
                if not isinstance(books, dict):
                    continue
                for slug, book in books.items():
                    if not isinstance(book, dict):
                        continue
                    price = _scalar(book.get("decimal_odds"))
                    if price is None or price <= 0:
                        continue
                    quotes.append(
                        {
                            "market": canonical_market,
                            "outcome": canonical_outcome,
                            "line": line,
                            "price": price,
                            # The grid publishes no per-bookmaker implied
                            # probability, and deriving one here would put a
                            # computed number in a field the other path fills
                            # from the provider.
                            "implied_probability": None,
                            "bookmaker_slug": str(slug),
                            # The grid keys each bookmaker by slug and carries a
                            # display name only for the best-priced one, so every
                            # other quote is honestly nameless rather than given
                            # a title-cased guess at its slug.
                            "bookmaker_name": best_name if str(slug) == best_slug else None,
                            "is_best": str(slug) == best_slug,
                            "updated_at": str(book.get("updated_at") or "") or None,
                        }
                    )

        bookmakers_count = payload.get("bookmakers_count")
        return self._bundle_result(
            result=result,
            parser_version=ODDS_COMPARISON_PARSER_VERSION,
            operation_name="odds_comparison",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "entitlement": "ENTITLED",
                "quotes": quotes,
                "bookmakers_count": int(bookmakers_count)
                if isinstance(bookmakers_count, int)
                else 0,
                "unknown_markets": unknown_markets,
            },
            parser_diagnostics={
                "entitlement": "ENTITLED",
                "accepted_count": len(quotes),
                "markets_count": len(markets),
                "unknown_markets": unknown_markets,
            },
            # An event with no odds answers ``{"markets": {}}`` (documented, and
            # seen live). That is a real, entitled answer meaning "nobody has
            # priced this yet" -- not an error, and the entitlement it proves
            # must survive into the caller.
            forced_status=None if quotes else SourceResultStatus.VALID_EMPTY,
        )

    def get_prediction_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """The CatBoost forecast for one event, rescaled to 0-1 probabilities.

        Only the ``corners`` block overlaps a market this pipeline prices, and it
        is the reason this endpoint is called at all: it is a methodologically
        independent second opinion on the one market where our own historical
        hit-rate can be checked against both a real price and a real model.

        Nulls are preserved as nulls the whole way down. The model publishes them
        where it lacks history -- the entire ``corners`` block is documented null
        when neither team history nor a market line exists -- and a null quietly
        defaulted to 0.5 would be indistinguishable from a genuine coin flip.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/prediction/",
            params={},
            operation="model_prediction",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        if not isinstance(payload.get("markets"), dict):
            return self._schema_error(result, "markets_not_object")

        prediction = _parse_prediction_row(payload)
        has_corners = _has_corners(prediction)
        return self._bundle_result(
            result=result,
            parser_version=PREDICTION_PARSER_VERSION,
            operation_name="model_prediction",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "prediction": prediction,
                "has_corners": has_corners,
            },
            parser_diagnostics={
                "has_corners": has_corners,
                "model_version": prediction["model_version"],
            },
        )

    def get_predictions_list_result(
        self,
        *,
        date: str,
        limit: int = MAX_PAGE_SIZE,
        offset: int = 0,
    ) -> SourceOperationResult[dict[str, Any]]:
        """Every published forecast for one betting day, keyed by native event id.

        The same content ``/events/{id}/prediction/`` serves one fixture at a
        time: measured live 2026-08-30, **146 predictions for a single date in
        one request**. MARKET_CONTEXT prefetches this once and falls back to the
        per-event endpoint only for fixtures the list did not cover, which turns
        the stage's per-event cost from four calls into three.

        **This takes a betting day, not a range, and that is a guard rather than
        a convenience.** ``date_to`` is compared against a *datetime*, so the
        provider reads it as midnight at the **start** of that day: asking for
        ``date_from=date_to=2026-08-31`` returns the fixtures kicking off at
        exactly 00:00 -- one row -- and looks precisely like a day the model has
        not got round to forecasting yet. The correct window for day D is
        ``[D, D+1]``, and it is computed here so no caller can get it wrong.
        Measured on 2026-08-31: 1 row the naive way, 46 the correct way.

        Rows whose event id cannot be read are skipped rather than guessed at --
        an unkeyed prediction cannot be attached to a fixture, and attaching it
        to the wrong one is the only outcome worse than not having it.
        """
        result = self._request_with_evidence(
            endpoint="/predictions/",
            params={
                "date_from": date,
                "date_to": _next_day(date),
                "limit": min(int(limit), MAX_PAGE_SIZE),
                "offset": max(int(offset), 0),
            },
            operation="model_prediction_listing",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("results")
        if not isinstance(rows, list):
            return self._schema_error(result, "results_not_list")

        predictions: dict[str, dict[str, Any]] = {}
        with_corners = 0
        off_day = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            event = row.get("event")
            event = event if isinstance(event, dict) else {}
            event_id = str(event.get("id") or "").strip()
            if not event_id:
                continue
            # The inclusive upper bound admits fixtures kicking off at exactly
            # 00:00 on the following day. One row, every time, and it would
            # otherwise be silently attributed to this betting day.
            if not str(event.get("event_date") or "").startswith(date):
                off_day += 1
                continue
            parsed = _parse_prediction_row(row)
            predictions[event_id] = parsed
            if _has_corners(parsed):
                with_corners += 1

        return self._bundle_result(
            result=result,
            parser_version=PREDICTION_PARSER_VERSION,
            operation_name="model_prediction_listing",
            source_event_refs=namespaced_source_refs(self.api_name, sorted(predictions)),
            value={
                "predictions": predictions,
                "total_count": payload.get("count") or 0,
                "returned_count": len(predictions),
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(predictions),
                "with_corners": with_corners,
                "off_day_dropped": off_day,
            },
            forced_status=None if predictions else SourceResultStatus.VALID_EMPTY,
        )

    # --------------------------------------------------------------- standings

    def get_standings_result(
        self, league_id: str | int, *, season_id: str | int | None = None
    ) -> SourceOperationResult[dict[str, Any]]:
        """A league table, carrying season **expected goals** and recent form.

        Worth one call per *league* — not per fixture — because it is the only
        place this API states a team's season-level xG. Everything else the
        pipeline holds is per finished match, so a side's underlying quality has
        to be re-derived from the same ten observations a hit rate already uses.

        ``xg_games`` is the sample behind ``xgf``/``xga`` and is carried for the
        same reason a referee's ``matches`` is: early in a season these are two-
        or three-match figures wearing a decimal point.

        ``form`` is the provider's own recent-results string (``"WWLDW"``),
        newest first.

        **Two payload shapes, and the second one is not rare.** A flat league
        answers ``{"grouped": false, "standings": [...]}``; a league played in
        groups answers ``{"grouped": true, "groups": {"Group A": [...], ...}}``
        and carries **no ``standings`` key at all**. Argentina's Primera is the
        second kind, and treating its absent ``standings`` as a schema error --
        which is what happened on 2026-08-30 -- silently drops season xG for
        every fixture in every grouped competition. Both are parsed here into
        one flat ``{team_id: row}`` map; the group name travels on the row.
        """
        params: dict[str, Any] = {}
        if season_id is not None:
            params["season_id"] = season_id
        result = self._request_with_evidence(
            endpoint=f"/leagues/{league_id}/standings/",
            params=params or None,
            operation="league_standings",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        # (group_name_or_empty, rows) pairs, covering both payload shapes.
        sections: list[tuple[str, list[Any]]] = []
        flat = payload.get("standings")
        groups = payload.get("groups")
        if isinstance(flat, list):
            sections.append(("", flat))
        elif isinstance(groups, dict):
            sections.extend(
                (str(name), rows) for name, rows in groups.items() if isinstance(rows, list)
            )
        elif isinstance(groups, list):
            # Not seen live, but the key is documented as a container and a list
            # of {name, standings} objects is the other obvious encoding.
            for entry in groups:
                if isinstance(entry, dict) and isinstance(entry.get("standings"), list):
                    sections.append((str(entry.get("name") or ""), entry["standings"]))
        else:
            return self._schema_error(result, "standings_not_list")

        table: dict[str, dict[str, Any]] = {}
        raw_count = 0
        for group_name, rows in sections:
            raw_count += len(rows)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                team_id = str(row.get("team_id") or "").strip()
                if not team_id:
                    continue
                table[team_id] = {
                    "provider_team_id": team_id,
                    "group": group_name or None,
                    "team_name": str(row.get("team_name") or ""),
                    "position": _count(row.get("position")),
                    "played": _count(row.get("played")),
                    "points": _count(row.get("pts")),
                    "goals_for": _count(row.get("gf")),
                    "goals_against": _count(row.get("ga")),
                    "xgf": _scalar(row.get("xgf")),
                    "xga": _scalar(row.get("xga")),
                    "xgd": _scalar(row.get("xgd")),
                    "xg_games": _count(row.get("xg_games")),
                    "form": str(row.get("form") or "") or None,
                }

        season = payload.get("season")
        season = season if isinstance(season, dict) else {}
        return self._bundle_result(
            result=result,
            parser_version=STANDINGS_PARSER_VERSION,
            operation_name="league_standings",
            source_event_refs=[],
            value={
                "provider_league_id": str(league_id),
                "season_id": str(season.get("id") or "") or None,
                "table": table,
            },
            parser_diagnostics={
                "raw_count": raw_count,
                "accepted_count": len(table),
                "grouped": bool(payload.get("grouped")),
                "group_count": len(sections) if payload.get("grouped") else 0,
            },
            forced_status=None if table else SourceResultStatus.VALID_EMPTY,
        )

    # ----------------------------------------------------- event player stats

    def get_event_player_stats_result(
        self, event_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """Every player's box score for **one** match, in one request.

        Deliberately **not** wired into the player-prop path, and the reason is
        worth stating so it is not "optimised" in later: building a prop sample
        needs one player across N past matches, and
        ``/players/{id}/stats/`` already returns that whole history inline for a
        single call. This endpoint is the opposite cut -- N players across one
        match -- so swapping it in would turn one call per player into one call
        per historical fixture, and would still miss any player who did not
        feature in the matches sampled.

        It is here for the cuts the other endpoint cannot make: a whole match's
        box scores including substitutes and the opposition, with ``rating``,
        ``expected_goals`` and ``expected_assists`` alongside the countable
        fields. Prop-relevant keys are normalised through ``PLAYER_STAT_MAP`` so
        a consumer reads the same names as the rest of the pipeline.
        """
        result = self._request_with_evidence(
            endpoint=f"/events/{event_id}/player-stats/",
            params=None,
            operation="event_player_stats",
            source_event_id=str(event_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("player_stats")
        if not isinstance(rows, list):
            return self._schema_error(result, "player_stats_not_list")

        players: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            player_id = str(row.get("player_id") or "").strip()
            if not player_id:
                continue
            minutes = _count(row.get("minutes_played"))
            entry: dict[str, Any] = {
                "provider_player_id": player_id,
                "provider_team_id": str(row.get("team_id") or "") or None,
                "minutes_played": minutes,
                "rating": _scalar(row.get("rating")),
                "expected_goals": _scalar(row.get("expected_goals")),
                "expected_assists": _scalar(row.get("expected_assists")),
            }
            for raw_key, (canonical, _unit) in PLAYER_STAT_MAP.items():
                entry[canonical] = _scalar(row.get(raw_key))
            players.append(entry)

        # Same rule the prop path applies: an unused substitute's box score is
        # all zeroes, and counting those makes every UNDER look like a lock.
        played = [p for p in players if (p["minutes_played"] or 0) > 0]
        return self._bundle_result(
            result=result,
            parser_version=EVENT_PLAYER_STATS_PARSER_VERSION,
            operation_name="event_player_stats",
            source_event_refs=namespaced_source_refs(self.api_name, [str(event_id)]),
            value={
                "provider_match_id": str(event_id),
                "players": players,
                "played_count": len(played),
            },
            parser_diagnostics={"raw_count": len(rows), "accepted_count": len(players)},
            forced_status=None if players else SourceResultStatus.VALID_EMPTY,
        )

    # ---------------------------------------------------------------- referees

    def get_referee_result(
        self, referee_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """One referee's season and career discipline averages.

        This is the only endpoint here that speaks directly to ``cards_total``
        and ``fouls_total``, the two markets where no provider gives the pipeline
        anything but the two clubs' own histories. Measured live 2026-08-30 on
        the same league: Peter Bankes averages 4.15 yellows and 22.1 fouls a
        match, Michael Oliver 3.10 and 23.2 -- a third of the spread in a cards
        line, decided by a man neither team's last ten says anything about.

        Free to address: every ``/events/`` row already carries ``referee_id``,
        so this costs one call per *referee*, not per fixture, and a referee
        works many fixtures a season.

        ``matches`` is the season sample and is the number to judge the averages
        by; a referee two games into a season has averages built on two games.
        The career totals are carried alongside precisely so that thinness is
        visible rather than hidden behind a confident-looking float.
        """
        result = self._request_with_evidence(
            endpoint=f"/referees/{referee_id}/",
            params=None,
            operation="referee_profile",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        if not str(payload.get("id") or "").strip():
            return self._schema_error(result, "referee_id_missing")

        profile = {
            "provider_referee_id": str(payload.get("id")),
            "name": str(payload.get("name") or ""),
            "country": payload.get("country") or None,
            "matches": _count(payload.get("matches")),
            "avg_yellow_per_match": _scalar(payload.get("avg_yellow_per_match")),
            "avg_red_per_match": _scalar(payload.get("avg_red_per_match")),
            "avg_fouls_per_match": _scalar(payload.get("avg_fouls_per_match")),
            "avg_goals_per_match": _scalar(payload.get("avg_goals_per_match")),
            "career_games": _count(payload.get("career_games")),
            "career_yellow_cards": _count(payload.get("career_yellow_cards")),
            "career_red_cards": _count(payload.get("career_red_cards")),
        }
        # A profile with a name but no averages is a real provider state (a
        # referee below the five-match floor), and it is VALID_EMPTY rather than
        # a schema error: nothing is malformed, there is simply nothing to read.
        has_averages = any(
            profile[key] is not None
            for key in ("avg_yellow_per_match", "avg_fouls_per_match", "avg_red_per_match")
        )
        return self._bundle_result(
            result=result,
            parser_version=REFEREE_PARSER_VERSION,
            operation_name="referee_profile",
            source_event_refs=[],
            value={"referee": profile},
            parser_diagnostics={
                "has_averages": has_averages,
                "season_matches": profile["matches"],
            },
            forced_status=None if has_averages else SourceResultStatus.VALID_EMPTY,
        )

    # ------------------------------------------------------------------ squads

    def get_team_squad_result(
        self, team_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """A team's squad, and the only structured absence feed in this API.

        ``availability`` / ``injury_type`` / ``injury_expected_return`` are what
        make this worth a call: the pipeline currently prices a fixture with no
        idea that four of the eleven are out. That matters most to the player
        props, where an absent player's prop is void rather than losing, and it
        matters to team totals through who actually takes the corners.

        Only genuinely unavailable players are counted (see
        ``UNAVAILABLE_STATUSES``). An empty ``availability`` means the provider
        published no report for that player and is **not** read as fit -- it is
        counted separately as ``unknown`` so a squad the provider covers thinly
        cannot masquerade as a fully fit one.
        """
        result = self._request_with_evidence(
            endpoint=f"/teams/{team_id}/squad/",
            params=None,
            operation="team_squad",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")
        rows = payload.get("players")
        if not isinstance(rows, list):
            return self._schema_error(result, "players_not_list")

        players: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []
        unknown = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            player_id = str(row.get("id") or "").strip()
            name = str(row.get("name") or "").strip()
            if not player_id or not name:
                continue
            availability = str(row.get("availability") or "").strip().lower()
            entry = {
                "provider_player_id": player_id,
                "player_name": name,
                "position": str(row.get("position") or ""),
                "availability": availability,
                "injury_type": str(row.get("injury_type") or "") or None,
                "injury_expected_return": row.get("injury_expected_return") or None,
            }
            players.append(entry)
            if availability in UNAVAILABLE_STATUSES:
                unavailable.append(entry)
            elif not availability:
                unknown += 1

        return self._bundle_result(
            result=result,
            parser_version=TEAM_SQUAD_PARSER_VERSION,
            operation_name="team_squad",
            source_event_refs=[],
            value={
                "provider_team_id": str(team_id),
                "players": players,
                "unavailable": unavailable,
                "squad_size": len(players),
                "unavailable_count": len(unavailable),
                "availability_unknown_count": unknown,
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(players),
                "unavailable_count": len(unavailable),
                "availability_unknown_count": unknown,
            },
            forced_status=None if players else SourceResultStatus.VALID_EMPTY,
        )


def _next_day(date: str) -> str:
    """``YYYY-MM-DD`` one day later, or the input unchanged if it is not a date.

    Exists for ``/predictions/``, whose ``date_to`` is compared against a
    datetime and therefore means "midnight starting that day". Returning the
    input unparsed rather than raising keeps a malformed date a provider-side
    404 instead of a crash mid-run.
    """
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return date
    return (parsed + timedelta(days=1)).strftime("%Y-%m-%d")


def _parse_prediction_row(payload: dict[str, Any]) -> dict[str, Any]:
    """One CatBoost forecast, rescaled to 0-1, from either prediction endpoint.

    ``/events/{id}/prediction/`` and a row of ``/predictions/`` carry an
    identical ``markets`` block, so the parsing lives here rather than in either
    method. That is not tidiness: the list endpoint exists to replace N per-event
    calls, and it can only do that safely if both paths produce a
    byte-identical prediction. Two parsers would drift, and the drift would show
    up as a corners signal that changed depending on how many fixtures the day
    happened to have.

    Nulls are preserved as nulls throughout. The model publishes them where it
    lacks history, and a null quietly defaulted to 0.5 would be
    indistinguishable from a model that looked at the match and called it even.
    """
    markets = payload.get("markets")
    markets = markets if isinstance(markets, dict) else {}

    def block(name: str) -> dict[str, Any]:
        value = markets.get(name)
        return value if isinstance(value, dict) else {}

    match_result = block("match_result")
    over_under = block("over_under")
    corners = block("corners")
    model = payload.get("model")
    model = model if isinstance(model, dict) else {}

    predicted = match_result.get("predicted")
    return {
        "prob_home": _percent(match_result.get("prob_home")),
        "prob_draw": _percent(match_result.get("prob_draw")),
        "prob_away": _percent(match_result.get("prob_away")),
        "predicted": predicted if predicted in ("H", "D", "A") else None,
        "xg_home": _scalar(block("expected_goals").get("home")),
        "xg_away": _scalar(block("expected_goals").get("away")),
        "prob_goals_over_15": _percent(over_under.get("prob_over_15")),
        "prob_goals_over_25": _percent(over_under.get("prob_over_25")),
        "prob_goals_over_35": _percent(over_under.get("prob_over_35")),
        "prob_btts_yes": _percent(block("btts").get("prob_yes")),
        "prob_dnb_home": _percent(block("draw_no_bet").get("prob_home")),
        "most_likely_score": block("score").get("most_likely") or None,
        "prob_corners_over_85": _percent(corners.get("prob_over_85")),
        "prob_corners_over_95": _percent(corners.get("prob_over_95")),
        "prob_corners_over_105": _percent(corners.get("prob_over_105")),
        "model_version": str(model.get("version") or "") or None,
        # Already 0-1 in the payload, unlike every probability above it.
        "model_confidence": _scalar(model.get("confidence")),
        "created_at": str(payload.get("created_at") or "") or None,
    }


def _has_corners(prediction: dict[str, Any]) -> bool:
    return any(
        prediction.get(key) is not None
        for key in ("prob_corners_over_85", "prob_corners_over_95", "prob_corners_over_105")
    )


def _percent(raw: Any) -> float | None:
    """A 0-100 model probability as a 0-1 fraction, or None.

    None in means None out, always. The provider publishes nulls where the model
    has too little history, and every one of them has to survive to the contract:
    the only alternative anyone reaches for is 0.5, which reads exactly like a
    model that looked at the match and called it even.
    """
    value = _scalar(raw)
    if value is None:
        return None
    return value / _PERCENT_TO_FRACTION


def _mark_best_quotes(quotes: list[dict[str, Any]]) -> None:
    """Flag the highest price in each (market, outcome, line) group, in place.

    Grouping includes the line, so the best price for over 8.5 corners is never
    compared against a quote on over 9.5. Ties leave the first-seen quote
    flagged; which of two identical prices is called best changes nothing about
    the price itself.
    """
    best_index: dict[tuple[str, str, float | None], int] = {}
    for index, quote in enumerate(quotes):
        key = (quote["market"], quote["outcome"], quote["line"])
        incumbent = best_index.get(key)
        if incumbent is None or quote["price"] > quotes[incumbent]["price"]:
            best_index[key] = index
    for index in best_index.values():
        quotes[index]["is_best"] = True


def _scalar(raw: Any) -> float | None:
    """A plain number, or None.

    Several ``stats`` fields are objects rather than scalars
    (``{"value": 7, "total": 13, "pct": 54}`` for dribbles, ``{"actual": 1.39,
    "estimated": true}`` for xg), so ``float()`` alone would raise on them. None
    of the mapped count metrics uses that shape, so an object is treated as
    absent rather than being guessed at.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError:
            return None
    return None


def _count(raw: Any) -> int | None:
    """A whole-number count, or None.

    Distinct from ``_scalar`` because the referee profile mixes the two: 4.15
    yellows a match is genuinely fractional, 27 matches is not. Rendering the
    sample size as ``27.0`` invites it to be read as an average like the field
    above it, which is the one confusion this data must not cause -- the sample
    size is what tells you whether to believe the averages at all.
    """
    value = _scalar(raw)
    return None if value is None else int(value)


def _normalize_event_row(
    row: Any, *, requested_team_id: str | None, source_order: int
) -> dict[str, Any] | None:
    """One ``/events/`` or ``/teams/{id}/fixtures/`` row in a shape the rest of
    the pipeline already reads (mirrors Highlightly's normalized match row)."""
    if not isinstance(row, dict):
        return None
    match_id = str(row.get("id") or "").strip()
    home_id = str(row.get("home_team_id") or "").strip()
    away_id = str(row.get("away_team_id") or "").strip()
    if not match_id or not home_id or not away_id or home_id == away_id:
        return None

    home_name = str(row.get("home_team") or "")
    away_name = str(row.get("away_team") or "")
    home_goals = row.get("home_score")
    away_goals = row.get("away_score")

    side = None
    opponent: dict[str, Any] = {"provider_team_id": None, "team_name": None}
    result_code = None
    if requested_team_id == home_id:
        side = "home"
        opponent = {"provider_team_id": away_id, "team_name": away_name}
        result_code = _infer_result(home_goals, away_goals)
    elif requested_team_id == away_id:
        side = "away"
        opponent = {"provider_team_id": home_id, "team_name": home_name}
        result_code = _infer_result(away_goals, home_goals)

    return {
        "provider_match_id": match_id,
        "kickoff": row.get("event_date"),
        "date": row.get("event_date"),
        "home_team": {"provider_team_id": home_id, "team_name": home_name},
        "away_team": {"provider_team_id": away_id, "team_name": away_name},
        "opponent": opponent,
        "home_away": side,
        "score": {"home": home_goals, "away": away_goals}
        if home_goals is not None and away_goals is not None
        else None,
        "result": result_code,
        "match_status": row.get("status"),
        "competition_provider_id": str(row.get("league_id"))
        if row.get("league_id") is not None
        else None,
        "season": row.get("season_id"),
        # Fixture context the provider already put in this row and that used to
        # be dropped on the floor here. None of it costs a request: it arrives
        # with every /events/ and /teams/{id}/fixtures/ page whether it is read
        # or not.
        #
        # referee_id is the reason this block exists -- it is the address for
        # /referees/{id}/, the only feed that says anything about cards or fouls
        # which is not one of the two clubs' own histories.
        "referee_id": str(row.get("referee_id")) if row.get("referee_id") is not None else None,
        "venue_id": str(row.get("venue_id")) if row.get("venue_id") is not None else None,
        "is_local_derby": bool(row.get("is_local_derby")),
        "is_neutral_ground": bool(row.get("is_neutral_ground")),
        "travel_distance_km": _scalar(row.get("travel_distance_km")),
        "weather": row.get("weather") if isinstance(row.get("weather"), dict) else None,
        "source_order": source_order,
    }


def _infer_result(goals_for: Any, goals_against: Any) -> str | None:
    if goals_for is None or goals_against is None:
        return None
    if goals_for > goals_against:
        return "W"
    if goals_for < goals_against:
        return "L"
    return "D"
