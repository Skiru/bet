"""Bzzoiro tennis client (``sports.bzzoiro.com/tennis/api/v2``).

One account and one credential (``BZZORIO_KEY``) as the football client, but a
separate product behind a separate path, with its own resource model
(``matches``/``player1``/``player2`` rather than ``events``/``home``/``away``)
and -- the fact that shapes every decision below -- **its own, far smaller quota
bucket**:

    ratelimit-policy: "tennis";q=100;w=86400      # verified live 2026-08-28

100 a day, not football's 7500. So this client is written to spend as few calls
as possible per event, and the difference is not cosmetic: at ~16 calls an event
the day's budget covers about six fixtures. Preflight reports that honestly
rather than promising a slate it cannot enrich.

Why it is worth having anyway: tennis was the weakest part of the pipeline.
``sackmann`` is dead (repo 404), ``NATIVE_ID_PROVIDERS_BY_SPORT["tennis"]`` was
empty, and the one live provider (``espn-tennis``) aliases only games and sets --
no aces, no double faults, no serve figures at all. This is the first tennis
source with native player ids instead of name matching, and
``GET /matches/{id}/`` returns a **complete box score in one request**: aces,
double faults, first/second-serve percentages, break points, service games,
points won, plus per-set splits. And because the payload is already
``p1_*``/``p2_*``, the per-player split arrives here in one wave -- football
needed a second one to stop summing the two sides.

Two shapes drive the code below and are easy to get wrong:

1. **``GET /matches/{id}/h2h/`` is the cheap listing.** Besides the pair's
   meetings it returns ``player1_last5`` *and* ``player2_last5``, each row
   carrying the match id, date, opponent, tournament and score. So one request
   serves all three enrichment slots. Two ``?player=`` listings would cost two
   requests for less.
2. **Those ``last5`` lists are relative to *now*, not to the match.** For the
   fixture 44426 (2026-08-01) they contained matches from 2026-08-15 and
   2026-08-17. Pricing a past date off that would put the future in the evidence,
   so the caller filters by date -- see ``fetch_bzzoiro_tennis_history``.
"""
from __future__ import annotations

from typing import Any

from bet.integration.evidence import namespaced_source_refs
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

from .base_client import BaseAPIClient
from .bzzoiro import _scalar, extract_quota_metadata
from .env import get_env
from .evidence_request import EvidenceRequestMixin
from .rate_limiter import RateLimiter

MATCHES_PARSER_VERSION = "bzzoiro-tennis-matches-v1"
MATCH_PARSER_VERSION = "bzzoiro-tennis-match-v1"
H2H_PARSER_VERSION = "bzzoiro-tennis-h2h-v1"

# Per-player box-score fields, without the ``p1_``/``p2_`` prefix the payload
# carries. Deliberately partial: the payload has ~20 fields a side (points in a
# row, receiver points, tiebreaks) and this pipeline prices totals.
PLAYER_STAT_FIELDS: dict[str, str] = {
    "aces": "aces",
    "double_faults": "double_faults",
    "games_won": "games_won",
    "service_games": "service_games",
    "service_games_won": "service_games_won",
    "first_serve_pct": "first_serve_pct",
    "first_serve_won_pct": "first_serve_won_pct",
    "break_points_saved_pct": "break_points_saved_pct",
    "break_points_converted_pct": "break_points_converted_pct",
}

# ``status`` values meaning the match was actually played out, so its box score
# describes tennis that happened. Surveyed live over four weeks: the others are
# ``walkover``, ``cancelled`` and ``scheduled`` (174 / 14 / 11 / 1), where a
# no-show or a retirement leaves a row that is real data about nothing.
#
# Checked against the *box score's own header*, not against the listing: the
# ``player1_last5`` rows this pipeline samples from carry ``won`` and a set score
# but no ``status`` field at all, so there is nothing to filter on until the
# match itself has been fetched. Football can pre-filter and save the call;
# tennis cannot, and pretending otherwise would mean filtering on a field that is
# always absent -- which passes everything.
FINISHED_STATUSES = frozenset({"finished"})

# Tournament categories this pipeline does not discover. A *denylist*, not an
# allowlist: the vocabulary seen live is grand_slam / masters_1000 / atp_500 /
# atp_250 / wta_1000 / wta_500 / wta_250 / challenger / other / utr, and a new
# tier the provider adds later should default to *visible* rather than silently
# vanish. What is excluded is amateur tennis nobody prices -- UTR alone was 47%
# of one four-week sample, and at 100 calls a day letting it into discovery
# would spend the whole tennis budget on it.
EXCLUDED_CATEGORIES = frozenset({"utr", "itf", "exhibition"})

# ``limit`` cap, mirroring the football product.
MAX_PAGE_SIZE = 200


class BzzoiroTennisClient(EvidenceRequestMixin, BaseAPIClient):
    """Tennis-only client for Bzzoiro's v2 REST API."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="bzzoiro-tennis",
            base_url="https://sports.bzzoiro.com/tennis/api/v2",
            rate_limiter=rate_limiter,
        )

    def _load_api_key(self) -> str | None:
        # The same credential as the football product -- one account, two APIs.
        # The provider name differs (bzzoiro-tennis) so the daily counter and the
        # BET_LIMIT_ override are separate, which is what the two different quota
        # buckets require.
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

    # BaseAPIClient's abstract surface. This client is reached through the
    # *_result methods below.
    def get_fixtures(self, date: str) -> list:
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Not addressable by a player pair: this API's H2H hangs off a *match*
        id (``get_h2h_result``), which is also what makes it cheap -- the same
        response carries both players' recent form."""
        return []

    # ----------------------------------------------------------------- listing

    def get_matches_result(
        self,
        *,
        date_from: str,
        date_to: str,
        status: str | None = None,
        limit: int = MAX_PAGE_SIZE,
        offset: int = 0,
    ) -> SourceOperationResult[dict[str, Any]]:
        """One page of ``/matches/``, normalized. Used by DISCOVER.

        ``total_count`` is reported because this listing, like the football one,
        pages **ascending** by date.
        """
        params: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "limit": min(int(limit), MAX_PAGE_SIZE),
            "offset": int(offset),
        }
        if status is not None:
            params["status"] = status

        result = self._request_with_evidence(
            endpoint="/matches/", params=params, operation="match_discovery"
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
            normalized = _normalize_match_row(row, source_order=index)
            if normalized is None:
                rejected_count += 1
                continue
            matches.append(normalized)

        total_count = payload.get("count")
        return self._bundle_result(
            result=result,
            parser_version=MATCHES_PARSER_VERSION,
            operation_name="match_discovery",
            source_event_refs=namespaced_source_refs(
                self.api_name, [item["provider_match_id"] for item in matches]
            ),
            value={
                "total_count": int(total_count)
                if isinstance(total_count, int)
                else len(matches),
                "offset": int(params["offset"]),
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

    # --------------------------------------------------------------- box score

    def get_match_result(
        self, match_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """``/matches/{id}/`` -- the whole box score in one request.

        Football needs two calls for this (the fixture, then its stats); here the
        detail endpoint already carries both, which is the single biggest reason
        this provider fits inside a 100-call day at all.

        The per-player split is preserved (``sides["p1"]`` / ``sides["p2"]``) and
        nothing is summed here. Whether a metric is a match total or one player's
        own line is a question about the *market*, and it is answered in
        ``simple_stats/providers.py`` where both readings are wanted.
        """
        result = self._request_with_evidence(
            endpoint=f"/matches/{match_id}/",
            params={},
            operation="detailed_metrics",
            source_event_id=str(match_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")

        header = _normalize_match_row(payload, source_order=1)
        if header is None:
            return self._schema_error(result, "match_row_unusable")

        sides: dict[str, dict[str, float]] = {}
        for prefix, side in (("p1_", "p1"), ("p2_", "p2")):
            side_stats: dict[str, float] = {}
            for field, normalized_name in PLAYER_STAT_FIELDS.items():
                value = _scalar(payload.get(f"{prefix}{field}"))
                if value is not None:
                    side_stats[normalized_name] = value
            sides[side] = side_stats

        # Sets played, from the set score rather than from any per-side stat.
        sets = {
            "p1": _scalar(payload.get("player1_sets")),
            "p2": _scalar(payload.get("player2_sets")),
        }

        if not sides["p1"] and not sides["p2"]:
            # A walkover or a cancelled match: the row exists, the box score does
            # not. Reported as a schema error so the caller can count it the same
            # way it counts football fixtures with no published stats.
            return self._schema_error(result, "statistics_empty")

        return self._bundle_result(
            result=result,
            parser_version=MATCH_PARSER_VERSION,
            operation_name="detailed_metrics",
            source_event_refs=namespaced_source_refs(self.api_name, [str(match_id)]),
            value={
                "provider_match_id": str(match_id),
                "match": header,
                "sides": sides,
                "sets": sets,
                "accepted_count": len(sides["p1"]) + len(sides["p2"]),
            },
            parser_diagnostics={
                "p1_fields": len(sides["p1"]),
                "p2_fields": len(sides["p2"]),
                "status": header.get("match_status"),
            },
        )

    # --------------------------------------------------------- h2h + form list

    def get_h2h_result(
        self, match_id: str | int
    ) -> SourceOperationResult[dict[str, Any]]:
        """``/matches/{id}/h2h/`` -- the pair's meetings **and** both players'
        recent form, in one request.

        This is the listing for all three enrichment slots. ``player1_last5`` and
        ``player2_last5`` each carry the match id, date, opponent and tournament
        of five recent matches, so a ``?player=`` listing per side would spend two
        requests to learn less.

        ``h2h`` is ``null`` when the two have never met, which is common and not
        an error; the form lists are the useful part either way.

        **The form lists are relative to now, not to this match.** They are
        returned unfiltered and dated, and the caller drops anything at or after
        the fixture's own date -- otherwise re-running an old date prices it with
        matches played afterwards.
        """
        result = self._request_with_evidence(
            endpoint=f"/matches/{match_id}/h2h/",
            params={},
            operation="historical_form_h2h",
            source_event_id=str(match_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")

        players = {
            "p1": _normalize_player(payload.get("player1")),
            "p2": _normalize_player(payload.get("player2")),
        }
        form = {
            side: _normalize_form_rows(payload.get(key))
            for side, key in (("p1", "player1_last5"), ("p2", "player2_last5"))
        }
        h2h = _normalize_form_rows(payload.get("h2h"))

        if not form["p1"] and not form["p2"] and not h2h:
            return self._schema_error(result, "h2h_and_form_empty")

        refs = [row["provider_match_id"] for row in (*form["p1"], *form["p2"], *h2h)]
        return self._bundle_result(
            result=result,
            parser_version=H2H_PARSER_VERSION,
            operation_name="historical_form_h2h",
            source_event_refs=namespaced_source_refs(self.api_name, refs),
            value={
                "provider_match_id": str(match_id),
                "players": players,
                "form": form,
                "h2h": h2h,
            },
            parser_diagnostics={
                "p1_form": len(form["p1"]),
                "p2_form": len(form["p2"]),
                "h2h": len(h2h),
            },
        )


def _normalize_player(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    player_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not player_id or not name:
        return None
    ranking = raw.get("current_ranking")
    return {
        "provider_player_id": player_id,
        "player_name": name,
        "country_code": raw.get("country_code"),
        "ranking": ranking.get("position") if isinstance(ranking, dict) else None,
    }


def _normalize_tournament(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "provider_tournament_id": str(raw["id"]) if raw.get("id") is not None else None,
        "name": str(raw.get("name") or ""),
        "circuit": raw.get("circuit"),
        # Carried through to the analyst: surface changes which total makes
        # sense (clay lengthens rallies and matches, grass shortens them), and
        # nothing downstream could recover it from the metric values.
        "category": (str(raw.get("category") or "")).lower(),
        "surface": (str(raw.get("surface") or "")).lower(),
    }


def _normalize_match_row(raw: Any, *, source_order: int) -> dict[str, Any] | None:
    """One ``/matches/`` or ``/matches/{id}/`` row in a stable shape."""
    if not isinstance(raw, dict):
        return None
    match_id = str(raw.get("id") or "").strip()
    player_one = _normalize_player(raw.get("player1"))
    player_two = _normalize_player(raw.get("player2"))
    if not match_id or player_one is None or player_two is None:
        return None
    if player_one["provider_player_id"] == player_two["provider_player_id"]:
        return None

    return {
        "provider_match_id": match_id,
        "date": raw.get("match_date"),
        "kickoff": raw.get("match_date"),
        "match_status": (str(raw.get("status") or "")).lower(),
        "player_one": player_one,
        "player_two": player_two,
        "tournament": _normalize_tournament(raw.get("tournament")),
        # Every row carries this flag. The pipeline has no concept of a doubles
        # pair anywhere (neither DiscoveredEvent nor EventRecord models one), so
        # it is surfaced here for discovery to drop rather than quietly treated
        # as a singles match between two of the four players.
        "is_doubles": bool(raw.get("is_doubles")),
        "sets": {
            "p1": raw.get("player1_sets"),
            "p2": raw.get("player2_sets"),
        },
        "source_order": source_order,
    }


def _normalize_form_rows(raw: Any) -> list[dict[str, Any]]:
    """``player1_last5`` / ``player2_last5`` / ``h2h`` rows.

    A different, flatter shape than ``/matches/``: one ``opponent`` instead of
    ``player1``/``player2``, and ``date`` instead of ``match_date``. Normalized to
    carry the id, the date and the opponent -- which is exactly what the caller
    needs to date a box score without spending a request on it.
    """
    if not isinstance(raw, list):
        return []
    rows = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        match_id = str(item.get("id") or "").strip()
        if not match_id:
            continue
        opponent = _normalize_player(item.get("opponent"))
        rows.append(
            {
                "provider_match_id": match_id,
                "date": item.get("date"),
                "opponent": opponent,
                "tournament": _normalize_tournament(item.get("tournament")),
                "surface": (str(item.get("surface") or "")).lower(),
                "round": item.get("round"),
                "won": item.get("won"),
                "source_order": index,
            }
        )
    return rows
