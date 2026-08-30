"""DISCOVER: collect football/tennis events for a date, dedup, classify identity.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 0). Odds are ignored
even where a source returns them (section 2: "Kursy ignorujemy").
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.bzzoiro_tennis import (
    EXCLUDED_CATEGORIES as _BZZOIRO_TENNIS_EXCLUDED_CATEGORIES,
)
from bet.api_clients.bzzoiro_tennis import BzzoiroTennisClient
from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture
from bet.discovery.sources.base import AbstractSourceAdapter
from bet.discovery.sources.odds_api import BASE_URL as ODDS_API_BASE_URL
from bet.discovery.sources.odds_api import OddsAPIAdapter
from bet.integration.source_result import SourceResultStatus

from bet.simple_stats.contracts import EventListV1, EventRecord, FixtureContext

logger = logging.getLogger(__name__)

_AMBIGUOUS_WINDOW_SECONDS = 6 * 3600

# Highlightly's per-page cap on /matches; the endpoint pages via `offset`.
_HIGHLIGHTLY_PAGE_SIZE = 100
_HIGHLIGHTLY_MAX_PAGES = 5

# Bzzoiro caps `limit` at 200 server-side (a request for 500 answered with 200).
# A day's whole football slate is well under one page -- 54 fixtures on
# 2026-08-28 -- so the page loop exists for the outlier, not the normal case.
_BZZOIRO_PAGE_SIZE = 200
_BZZOIRO_MAX_PAGES = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_id(sport: str, competition: str, participants: str, start_time: str) -> str:
    raw = f"{sport}|{competition}|{participants}|{start_time}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_name(name: str | None) -> str:
    return " ".join((name or "").strip().lower().split())


class OddsAPIEventsAdapter(OddsAPIAdapter):
    """The Odds API schedule source that reads the *free* ``/events`` endpoint
    instead of the credit-charged ``/odds`` one the parent uses.

    Section 4.3 of the plan calls The Odds API "główny terminarz, pole `odds`
    ignorowane" -- this pipeline never reads a price, so paying a credit per
    league per run to receive bookmaker payloads it discards is pure waste.
    It is also, concretely, why DISCOVER returned zero events: the account's
    500-request monthly quota is spent, so ``/odds`` answers 401
    OUT_OF_USAGE_CREDITS while ``/events`` (0 credits, per The Odds API's
    usage-quota docs) keeps answering 200 with exactly the schedule fields
    EVENT_LIST_V1 needs (id / sport_title / commence_time / home_team /
    away_team).
    """

    def _fetch_for_key(self, sport_key: str, sport: str, date: str) -> list[DiscoveredEvent]:
        try:
            resp = requests.get(
                f"{ODDS_API_BASE_URL}/sports/{sport_key}/events",
                params={"apiKey": self._api_key, "dateFormat": "iso"},
                timeout=20,
            )
        except requests.RequestException as exc:
            self._record_error(f"request failed for {sport_key}: {exc}")
            return []

        if resp.status_code == 401:
            self._auth_failed = True
            self._record_error("auth failed (401) on /events — key invalid")
            return []
        if resp.status_code in (404, 422):
            return []
        if resp.status_code >= 400:
            self._record_error(f"{sport_key}: HTTP {resp.status_code}")
            return []

        try:
            items = resp.json()
        except (ValueError, json.JSONDecodeError):
            self._record_error(f"{sport_key}: non-JSON body")
            return []

        events: list[DiscoveredEvent] = []
        for item in items:
            try:
                kickoff = datetime.fromisoformat(
                    str(item.get("commence_time", "")).replace("Z", "+00:00")
                )
                if kickoff.strftime("%Y-%m-%d") != date:
                    continue
                events.append(
                    DiscoveredEvent(
                        source=self.name,
                        external_id=item.get("id", ""),
                        sport=sport,
                        competition=item.get("sport_title", ""),
                        home_team=item.get("home_team", "") or "",
                        away_team=item.get("away_team", "") or "",
                        kickoff=kickoff,
                        status="scheduled",
                        raw_data={"sport_key": sport_key},
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one malformed row must not drop the page
                self.logger.debug("Skipping Odds API event: %s", exc)
                continue
        return events


class HighlightlyDiscoveryAdapter(AbstractSourceAdapter):
    """Discovery source reading Highlightly's ``/matches?date=`` page.

    The client's own ``discover_matches_result`` is scoped to a single
    ``leagueId``/``season`` pair (api_clients/highlightly.py:390-397), which
    would require hand-maintaining a league list and would silently miss the
    "mecze spoza głównych lig" this source exists to catch (section 4.3). The
    underlying endpoint does accept a plain ``date`` filter, so this adapter
    queries it directly through the client's authenticated session
    (``_build_headers`` / ``base_url``), paging via ``offset``.

    Each event's ``raw_data`` carries Highlightly's native match id *and* both
    native team ids, which ENRICH needs to call /statistics, /last-five-games
    and /head-2-head for this provider at all.
    """

    name = "highlightly"
    priority = 5
    supported_sports = ["football"]

    def __init__(self, rate_limiter: RateLimiter):
        self._client = HighlightlyClient(rate_limiter=rate_limiter)
        super().__init__()

    def is_available(self) -> bool:
        return bool(self._client.api_key)

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        if sport != "football":
            return []

        headers = self._client._build_headers()
        events: list[DiscoveredEvent] = []
        for page in range(_HIGHLIGHTLY_MAX_PAGES):
            offset = page * _HIGHLIGHTLY_PAGE_SIZE
            try:
                resp = requests.get(
                    f"{self._client.base_url}/matches",
                    params={"date": date, "limit": _HIGHLIGHTLY_PAGE_SIZE, "offset": offset},
                    headers=headers,
                    timeout=25,
                )
                resp.raise_for_status()
                rows = resp.json().get("data") or []
            except (requests.RequestException, ValueError) as exc:
                self._record_error(f"page offset={offset}: {exc}")
                break

            for row in rows:
                home = row.get("homeTeam") or {}
                away = row.get("awayTeam") or {}
                league = row.get("league") or {}
                try:
                    kickoff = datetime.fromisoformat(
                        str(row.get("date", "")).replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if not home.get("name") or not away.get("name"):
                    continue
                events.append(
                    DiscoveredEvent(
                        source=self.name,
                        external_id=str(row.get("id", "")),
                        sport="football",
                        competition=league.get("name") or "",
                        home_team=home["name"],
                        away_team=away["name"],
                        kickoff=kickoff,
                        status=(row.get("state") or {}).get("description") or "scheduled",
                        raw_data={
                            "provider_match_id": str(row.get("id", "")),
                            "home_team_id": str(home.get("id", "")),
                            "away_team_id": str(away.get("id", "")),
                            "league_id": str(league.get("id", "")),
                            "season": league.get("season"),
                        },
                    )
                )

            if len(rows) < _HIGHLIGHTLY_PAGE_SIZE:
                break
        return events


class BzzoiroDiscoveryAdapter(AbstractSourceAdapter):
    """Discovery source reading Bzzoiro's ``/events/?date_from=&date_to=`` page.

    Exists for two reasons beyond volume. First, the quota: Highlightly's 100
    calls a day is what left 175 of 181 events BLOCKED on 2026-08-25, and this
    provider publishes 7500. Second, and the reason it changes which bets are
    reachable at all: Champions League, Europa League and Conference League are
    first-class leagues here with their own ids, so the qualifying fixtures that
    produced the winning coupons are discovered directly -- with no entry in
    ``config/sportdb_competition_map.json`` and no fuzzy name pin, because the
    provider names the competition itself.

    Each event's ``raw_data`` carries the native match id and both native team
    ids. ``_to_event_record``'s generic loop lifts those into
    ``EventRecord.provider_team_ids["bzzoiro"]`` with no provider-specific code,
    which is what lets ENRICH address this provider by id.
    """

    name = "bzzoiro"
    priority = 4
    supported_sports = ["football"]

    def __init__(self, rate_limiter: RateLimiter):
        self._client = BzzoiroClient(rate_limiter=rate_limiter)
        self._league_names: dict[str, str] | None = None
        super().__init__()

    def is_available(self) -> bool:
        return bool(self._client.api_key)

    def _league_name(self, league_id: str) -> str:
        """Competition name for a ``league_id``, from one cached catalogue call.

        ``/events/`` names a fixture's competition only by id, and
        ``EventRecord.competition`` feeds the event id, the dedup key and every
        downstream competition lookup. The whole catalogue is 83 rows and fits in
        a single request, so this costs one call per adapter instance -- as
        against one per fixture, or a hand-maintained id->name table that would
        silently rot the first time the provider adds a league.
        """
        if self._league_names is None:
            self._league_names = {}
            result = self._client.get_leagues_result()
            if result.status is SourceResultStatus.SUCCESS and result.value:
                self._league_names = {
                    row["provider_league_id"]: row["league_name"]
                    for row in result.value.get("leagues", [])
                }
            else:
                self._record_error(
                    f"league catalogue unavailable ({getattr(result.status, 'value', result.status)}): "
                    "events will carry their numeric league id as competition"
                )
        return self._league_names.get(league_id, "")

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        if sport != "football":
            return []

        events: list[DiscoveredEvent] = []
        for page in range(_BZZOIRO_MAX_PAGES):
            result = self._client.get_events_result(
                date_from=date,
                date_to=date,
                limit=_BZZOIRO_PAGE_SIZE,
                offset=page * _BZZOIRO_PAGE_SIZE,
            )
            if result.status not in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
                self._record_error(
                    f"page {page}: {getattr(result.status, 'value', result.status)}"
                    f" ({result.error_code})"
                )
                break
            matches = (result.value or {}).get("matches") or []
            for row in matches:
                try:
                    kickoff = datetime.fromisoformat(
                        str(row.get("date") or "").replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                home = row["home_team"]
                away = row["away_team"]
                if not home.get("team_name") or not away.get("team_name"):
                    continue
                league_id = str(row.get("competition_provider_id") or "")
                events.append(
                    DiscoveredEvent(
                        source=self.name,
                        external_id=row["provider_match_id"],
                        sport="football",
                        # Falling back to "bzzoiro-league-<id>" rather than "" so
                        # a catalogue outage degrades to an ugly-but-unique
                        # competition name instead of collapsing every fixture
                        # of the day into one empty-named competition, which is
                        # what the dedup key and the event id are built from.
                        competition=self._league_name(league_id)
                        or (f"bzzoiro-league-{league_id}" if league_id else ""),
                        home_team=home["team_name"],
                        away_team=away["team_name"],
                        kickoff=kickoff,
                        status=str(row.get("match_status") or "scheduled"),
                        raw_data={
                            "provider_match_id": row["provider_match_id"],
                            "home_team_id": home["provider_team_id"],
                            "away_team_id": away["provider_team_id"],
                            "league_id": league_id,
                            "season": row.get("season"),
                            # Carried from the same /events/ row, at no extra
                            # request. referee_id is the one that changes a
                            # betting read: it is the address for
                            # /referees/{id}/, and cards and fouls are the two
                            # markets with no corroborating provider at all.
                            "referee_id": row.get("referee_id"),
                            "venue_id": row.get("venue_id"),
                            "is_local_derby": row.get("is_local_derby"),
                            "is_neutral_ground": row.get("is_neutral_ground"),
                            "travel_distance_km": row.get("travel_distance_km"),
                            "weather": row.get("weather"),
                        },
                    )
                )

            total = (result.value or {}).get("total_count") or 0
            if len(matches) < _BZZOIRO_PAGE_SIZE or (page + 1) * _BZZOIRO_PAGE_SIZE >= total:
                break
        return events


class BzzoiroTennisDiscoveryAdapter(AbstractSourceAdapter):
    """Discovery source reading Bzzoiro's tennis ``/matches/`` page.

    The first tennis source that hands over **native player ids**. Until now the
    only tennis schedule was The Odds API, whose ``raw_data`` carries just a
    sport key (nothing analogous to football's
    ``provider_team_ids["highlightly"]``), so every tennis provider had to
    re-find both players by name through a search endpoint.

    Two filters, both load-bearing:

    * **Doubles are dropped.** Every row carries ``is_doubles``, and nothing in
      the pipeline models a pair -- ``DiscoveredEvent`` and ``EventRecord`` both
      have exactly two participants. A doubles match let through would dedup
      against a singles fixture between two of the same four players and pollute
      the sample.
    * **Amateur tiers are dropped** (``EXCLUDED_CATEGORIES``: utr, itf,
      exhibition). This is a discovery filter rather than a display preference
      because the tennis quota is 95 calls a day, about six enriched fixtures,
      and UTR was 47% of one four-week sample -- discovering it would spend the
      budget on tennis nobody prices. Challenger and above are kept, and an
      unknown new tier is kept too.
    """

    name = "bzzoiro-tennis"
    priority = 4
    supported_sports = ["tennis"]

    def __init__(self, rate_limiter: RateLimiter):
        self._client = BzzoiroTennisClient(rate_limiter=rate_limiter)
        super().__init__()

    def is_available(self) -> bool:
        return bool(self._client.api_key)

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        if sport != "tennis":
            return []

        events: list[DiscoveredEvent] = []
        excluded_doubles = 0
        excluded_category = 0
        for page in range(_BZZOIRO_MAX_PAGES):
            result = self._client.get_matches_result(
                date_from=date,
                date_to=date,
                limit=_BZZOIRO_PAGE_SIZE,
                offset=page * _BZZOIRO_PAGE_SIZE,
            )
            if result.status not in (
                SourceResultStatus.SUCCESS,
                SourceResultStatus.VALID_EMPTY,
            ):
                self._record_error(
                    f"page {page}: {getattr(result.status, 'value', result.status)}"
                    f" ({result.error_code})"
                )
                break
            matches = (result.value or {}).get("matches") or []
            for row in matches:
                if row["is_doubles"]:
                    excluded_doubles += 1
                    continue
                tournament = row["tournament"]
                if tournament["category"] in _BZZOIRO_TENNIS_EXCLUDED_CATEGORIES:
                    excluded_category += 1
                    continue
                try:
                    kickoff = datetime.fromisoformat(
                        str(row.get("date") or "").replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                one, two = row["player_one"], row["player_two"]
                events.append(
                    DiscoveredEvent(
                        source=self.name,
                        external_id=row["provider_match_id"],
                        sport="tennis",
                        # Tournament name plus tier, because "Washington" alone
                        # collides across circuits and the tier is what tells a
                        # reader whether the fixture is worth a line at all.
                        competition=_tennis_competition_name(tournament),
                        home_team=one["player_name"],
                        away_team=two["player_name"],
                        kickoff=kickoff,
                        status=row["match_status"] or "scheduled",
                        # home_team_id / away_team_id, not player ids: these are
                        # the exact keys _to_event_record already reads, so the
                        # generic lift into provider_team_ids["bzzoiro-tennis"]
                        # needs no change there. The names are about the slot,
                        # not about the sport.
                        raw_data={
                            "provider_match_id": row["provider_match_id"],
                            "home_team_id": one["provider_player_id"],
                            "away_team_id": two["provider_player_id"],
                            "tournament_id": tournament["provider_tournament_id"],
                            "category": tournament["category"],
                            "surface": tournament["surface"],
                            "circuit": tournament["circuit"],
                        },
                    )
                )

            total = (result.value or {}).get("total_count") or 0
            if len(matches) < _BZZOIRO_PAGE_SIZE or (page + 1) * _BZZOIRO_PAGE_SIZE >= total:
                break

        if excluded_doubles or excluded_category:
            # Recorded rather than silent: "12 tennis events today" versus "124
            # rows, 94 of them UTR" are different facts about the day, and only
            # one of them explains a thin slate.
            self._record_error(
                f"filtered out {excluded_doubles} doubles and "
                f"{excluded_category} non-tour-level matches"
            )
        return events


def _tennis_competition_name(tournament: dict) -> str:
    """``"Washington (atp_500)"``. The tier is part of the name because
    EventRecord has nowhere else to put it, and it is what separates a tour
    event from a same-named challenger in the dedup key and the event id."""
    name = tournament.get("name") or ""
    category = tournament.get("category") or ""
    if name and category:
        return f"{name} ({category})"
    return name or (f"bzzoiro-tennis-{category}" if category else "")


def _fetch_source_events(source: AbstractSourceAdapter, date: str, sports: list[str]) -> list[DiscoveredEvent]:
    events: list[DiscoveredEvent] = []
    for sport in sports:
        if sport not in source.supported_sports:
            continue
        events.extend(source.fetch_events(date, sport))
    return events


def _fetch_all_sources(
    sources: list[AbstractSourceAdapter], date: str, sports: list[str]
) -> dict[str, list[DiscoveredEvent]]:
    events_by_source: dict[str, list[DiscoveredEvent]] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_fetch_source_events, src, date, sports): src.name for src in sources}
        for future in as_completed(futures):
            name = futures[future]
            try:
                events_by_source[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - one crashed source must not abort discovery
                logger.error("Discovery source %s crashed: %s", name, exc)
                events_by_source[name] = []
    return events_by_source


def _detect_ambiguous(
    events_by_source: dict[str, list[DiscoveredEvent]],
) -> tuple[list[EventRecord], dict[str, list[DiscoveredEvent]]]:
    """Group raw events by normalized (home, away) name pair across all
    sources; a group whose members disagree on sport or whose kickoffs are
    more than 6 hours apart is AMBIGUOUS/BLOCKED_IDENTITY and is pulled out
    of the pool before deduplication (section 2: "bez automatycznego wyboru
    'pierwszego' źródła")."""
    groups: dict[tuple[str, str], list[DiscoveredEvent]] = {}
    for events in events_by_source.values():
        for ev in events:
            key = (_normalize_name(ev.home_team), _normalize_name(ev.away_team))
            groups.setdefault(key, []).append(ev)

    blocked_ids: set[tuple[str, str]] = set()
    blocked_records: list[EventRecord] = []
    for (home, away), evs in groups.items():
        if len(evs) < 2:
            continue
        sports = {e.sport for e in evs}
        kickoffs = [e.kickoff for e in evs]
        spread_seconds = (max(kickoffs) - min(kickoffs)).total_seconds()
        reasons = []
        if len(sports) > 1:
            reasons.append(f"conflicting sport across sources: {sorted(sports)}")
        if spread_seconds > _AMBIGUOUS_WINDOW_SECONDS:
            reasons.append("conflicting start_time across sources")
        if not reasons:
            continue

        rep = evs[0]
        sport = rep.sport if rep.sport in ("football", "tennis") else "football"
        participants = f"{home}|{away}"
        record_kwargs = dict(
            event_id=_event_id(sport, rep.competition, participants, rep.kickoff.isoformat()),
            sport=sport,
            competition=rep.competition,
            start_time=rep.kickoff.isoformat(),
            source_ids={e.source: e.external_id for e in evs},
            identity_confidence="AMBIGUOUS",
            status="BLOCKED_IDENTITY",
            terminal_reason="; ".join(reasons),
        )
        if sport == "tennis":
            record_kwargs["player_one"] = rep.home_team
            record_kwargs["player_two"] = rep.away_team
        else:
            record_kwargs["home_team"] = rep.home_team
            record_kwargs["away_team"] = rep.away_team
        blocked_records.append(EventRecord(**record_kwargs))
        for e in evs:
            blocked_ids.add((e.source, e.external_id))

    filtered = {
        source: [e for e in events if (source, e.external_id) not in blocked_ids]
        for source, events in events_by_source.items()
    }
    return blocked_records, filtered


def _to_event_record(fixture: MergedFixture) -> EventRecord:
    sport = fixture.sport if fixture.sport in ("football", "tennis") else "football"
    participants = f"{_normalize_name(fixture.home_team)}|{_normalize_name(fixture.away_team)}"
    event_id = _event_id(sport, fixture.competition, participants, fixture.kickoff.isoformat())
    source_ids = {s.source: s.external_id for s in fixture.sources}

    # CONFIRMED requires 2+ sources agreeing on an identical native id (i.e.
    # the exact-key match path in DeduplicationEngine.merge, which leaves
    # confidence at its 1.0 default); anything merged only via fuzzy
    # name+time matching -- or found by a single source only -- is
    # FUZZY_MATCHED (section 2's rule has no separate bucket for
    # single-source events).
    if fixture.source_count >= 2 and all(s.confidence == 1.0 for s in fixture.sources):
        identity_confidence = "CONFIRMED"
    else:
        identity_confidence = "FUZZY_MATCHED"

    # Highlightly's stats endpoints are unusable without its native team ids
    # (see EventRecord.provider_team_ids), so lift them out of the SourceRef
    # raw_data the discovery adapter attached.
    provider_team_ids: dict[str, dict[str, str]] = {}
    fixture_context: FixtureContext | None = None
    for src in fixture.sources:
        raw = src.raw_data if isinstance(src.raw_data, dict) else {}
        home_id = str(raw.get("home_team_id") or "")
        away_id = str(raw.get("away_team_id") or "")
        if home_id and away_id and home_id != away_id:
            provider_team_ids[src.source] = {"home": home_id, "away": away_id}
        # Only bzzoiro publishes these, so there is no cross-source merge to do
        # and no precedence to decide: the fixture either was discovered there
        # or has no context block at all.
        if src.source == "bzzoiro" and raw.get("referee_id") is not None:
            fixture_context = FixtureContext(
                referee_id=raw.get("referee_id"),
                venue_id=raw.get("venue_id"),
                league_id=str(raw.get("league_id") or "") or None,
                is_local_derby=bool(raw.get("is_local_derby")),
                is_neutral_ground=bool(raw.get("is_neutral_ground")),
                travel_distance_km=raw.get("travel_distance_km"),
                weather=raw.get("weather"),
            )

    record_kwargs = dict(
        event_id=event_id,
        sport=sport,
        competition=fixture.competition,
        start_time=fixture.kickoff.isoformat(),
        source_ids=source_ids,
        provider_team_ids=provider_team_ids,
        identity_confidence=identity_confidence,
        status="ACTIVE",
        terminal_reason=None,
        fixture_context=fixture_context,
    )
    if sport == "tennis":
        record_kwargs["player_one"] = fixture.home_team
        record_kwargs["player_two"] = fixture.away_team
    else:
        record_kwargs["home_team"] = fixture.home_team
        record_kwargs["away_team"] = fixture.away_team
    return EventRecord(**record_kwargs)


def discover_events(
    date: str,
    sports: list[str] | None = None,
    rate_limiter: RateLimiter | None = None,
    run_id: str = "",
) -> EventListV1:
    """Discover football/tennis events for ``date`` from The Odds API, Highlightly
    and Bzzoiro (football and tennis are separate Bzzoiro products with separate
    quotas, hence two adapters), dedup them, and classify each merged fixture's
    identity confidence.

    SportDB is not a discovery source: its only schedule-shaped method,
    ``get_competition_results_with_evidence``, returns rows
    (provider_match_id / home_name / away_name / status / score -- verified
    live) that carry no date field, so a valid ``EventRecord.start_time``
    cannot be built from them without fabricating one. It is wired into
    ENRICH instead (section 4.1), where a match id is all it needs.
    """
    sports = list(sports) if sports else ["football", "tennis"]
    rate_limiter = rate_limiter or RateLimiter()

    sources: list[AbstractSourceAdapter] = [
        OddsAPIEventsAdapter(),
        HighlightlyDiscoveryAdapter(rate_limiter),
        BzzoiroDiscoveryAdapter(rate_limiter),
        BzzoiroTennisDiscoveryAdapter(rate_limiter),
    ]
    events_by_source = _fetch_all_sources(sources, date, sports)
    blocked_records, filtered = _detect_ambiguous(events_by_source)

    engine = DeduplicationEngine()
    merged = engine.merge(filtered)
    active_records = [_to_event_record(fixture) for fixture in merged]

    return EventListV1(
        run_id=run_id,
        generated_at=_now_iso(),
        date=date,
        sports=sports,
        events=active_records + blocked_records,
    )
