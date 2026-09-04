"""DISCOVER: collect football/tennis events for a date, dedup, classify identity.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 0). Odds are ignored
even where a source returns them (section 2: "Kursy ignorujemy").
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture
from bet.discovery.sources.base import AbstractSourceAdapter
from bet.discovery.sources.odds_api import BASE_URL as ODDS_API_BASE_URL
from bet.discovery.sources.odds_api import OddsAPIAdapter
from bet.integration.source_result import SourceResultStatus

from bet.simple_stats.contracts import (
    SLATE_CRITICAL_SOURCES,
    EventListV1,
    EventRecord,
    FixtureContext,
)

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


# docs/PLAN_BOGATE_STATYSTYKI.md Faza 6.
_COMPETITION_CANONICAL_MAP_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "competition_name_canonical_map.json"
)
_COMPETITION_CANONICAL_CACHE: dict[str, str] | None = None
_COMPETITION_CANONICAL_LOCK = threading.Lock()


def _competition_canonical_map() -> dict[str, str]:
    """``{raw name: canonical name}`` from config/competition_name_canonical_map.json,
    read once. Exact-name pin only, matching the same rule the ESPN and SportDB
    competition maps already follow. A missing or malformed file yields an
    empty map rather than raising -- a config problem must not block discovery.
    """
    global _COMPETITION_CANONICAL_CACHE
    with _COMPETITION_CANONICAL_LOCK:
        if _COMPETITION_CANONICAL_CACHE is not None:
            return _COMPETITION_CANONICAL_CACHE
    canonical: dict[str, str] = {}
    try:
        raw = _COMPETITION_CANONICAL_MAP_PATH.read_text(encoding="utf-8")
        document = json.loads(raw)
        canonical = {
            str(name): str(target)
            for name, target in (document.get("canonical") or {}).items()
        }
    except (OSError, ValueError, AttributeError):
        canonical = {}
    with _COMPETITION_CANONICAL_LOCK:
        if _COMPETITION_CANONICAL_CACHE is None:
            _COMPETITION_CANONICAL_CACHE = canonical
        return _COMPETITION_CANONICAL_CACHE


def reset_competition_canonical_cache() -> None:
    """Forget the cached competition-name canonical map. For tests only."""
    global _COMPETITION_CANONICAL_CACHE
    with _COMPETITION_CANONICAL_LOCK:
        _COMPETITION_CANONICAL_CACHE = None


def _canonicalize_competition_names(
    events_by_source: dict[str, list[DiscoveredEvent]],
) -> None:
    """Rewrite every DiscoveredEvent.competition through the exact-name pin map,
    in place, across all sources. Run before dedup and ESPN resolution both
    read it, so a league that arrives as "EPL" from one provider and
    "Premier League" from another gets one event_id and one competition-map
    lookup instead of two."""
    canonical = _competition_canonical_map()
    if not canonical:
        return
    for events in events_by_source.values():
        for ev in events:
            target = canonical.get(ev.competition)
            if target is not None:
                ev.competition = target


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


# League names that name no competition on their own. Highlightly hands these
# back bare, with the country sitting *beside* ``league`` on the fixture row
# rather than inside it -- so "Cup" arrived as the competition name for 41
# fixtures on 2026-09-02, from PAOK-OFI (Greece) to J-League Cup ties, all
# collapsed into one bucket. A name that cannot tell those apart cannot be
# pinned to a league code, cannot be scoped by ``observation_scope`` and cannot
# be checked by the ESPN pin gate, because there is nothing in it to check.
#
# Deliberately a closed list of *generic* words rather than a rule applied to
# every name. Qualifying unconditionally would rewrite "LaLiga" to "Spain
# LaLiga" and "Premier League" to "England Premier League" -- keys the
# competition tables already hold in their bare form, so a blanket prefix would
# break resolutions that work today in order to fix ones that do not.
#
# Note what this does and does not buy. It makes the name specific, which the
# scope and tier maps need; it does *not* by itself buy ESPN coverage, because
# ESPN serves no team directory for most national cups (pol.cup, rou.cup,
# swe.cup and a Japanese league cup code were all probed on 2026-09-02 and all
# 404).
_GENERIC_COMPETITION_NAMES = frozenset({
    "cup", "super cup", "supercup", "league cup", "fa cup", "national cup",
    "first league", "second league", "third league", "premier league",
    "first division", "second division", "primera division", "super league",
    "superliga", "premiership", "championship", "1st division", "2nd division",
    # Added 2026-09-02 from the slates themselves: bare "Serie A" was
    # Atletico-MG - Vitoria (Brazil, not Italy), bare "Ligue 1" was mostly
    # Algeria and Tunisia (not France), bare "Pro League" alternated between
    # Saudi Arabia, the UAE and Belgium. Each name resolved *confidently* to
    # the European code in the ESPN table -- the exact wire shape of the
    # "Cup" incident, but landing on a directory where a substring can cross
    # team identity ("inter" is inside "internacional"). The bare ESPN keys
    # are gone too; only the qualified forms resolve now.
    "serie a", "serie b", "ligue 1", "ligue 2", "pro league",
    "primera división",
})


def _highlightly_competition_name(league: dict, country: dict) -> str:
    """``league.name``, qualified by country when the name alone names nothing.

    Returns the bare name unchanged for everything else, so the exact-name pin
    maps keep matching the keys they already hold.
    """
    name = str(league.get("name") or "").strip()
    if not name:
        return ""
    country_name = str((country or {}).get("name") or "").strip()
    if not country_name:
        return name
    if name.casefold() not in _GENERIC_COMPETITION_NAMES:
        return name
    if country_name.casefold() in name.casefold():
        return name
    return f"{country_name} {name}"


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
        limiter = self._client.rate_limiter
        events: list[DiscoveredEvent] = []
        for page in range(_HIGHLIGHTLY_MAX_PAGES):
            offset = page * _HIGHLIGHTLY_PAGE_SIZE
            # This adapter calls ``requests.get`` directly rather than through
            # the client (the client's own discover_matches_result is scoped to
            # one leagueId/season, which is the whole reason this exists), and
            # until 2026-09-02 that meant three things the request path does
            # for free were simply not happening here:
            #
            #   * the daily quota was not *checked*, so a run with nothing left
            #     still fired five pages and collected five 429s;
            #   * the calls were not *recorded*, so ENRICH's budget decisions
            #     were made against a count up to five requests optimistic;
            #   * the response's own ``x-ratelimit-day-remaining`` was parsed
            #     nowhere, so the one authoritative number on the page was read
            #     and discarded.
            #
            # That matters more for this provider than for any other: it drives
            # discovery, so its exhaustion shrinks the slate by about 77% rather
            # than merely costing corroboration, and the counter drifting
            # optimistic is exactly how a run finds that out halfway through.
            if not limiter.can_request(self.name, 1):
                self._record_error(
                    f"daily quota exhausted before page offset={offset} "
                    f"({limiter.get_remaining(self.name)} left)"
                )
                break
            try:
                resp = requests.get(
                    f"{self._client.base_url}/matches",
                    params={"date": date, "limit": _HIGHLIGHTLY_PAGE_SIZE, "offset": offset},
                    headers=headers,
                    timeout=25,
                )
                limiter.record_request(self.name, "discover_matches", 1)
                # Reconciled from the provider's own answer, one-way (it can
                # only raise our count) -- see RateLimiter.
                # reconcile_from_provider. Done before raise_for_status, because
                # a 429 is the response that carries this header most usefully.
                quota = self._client._extract_quota_metadata(dict(resp.headers))
                if quota:
                    limiter.reconcile_from_provider(self.name, quota)
                resp.raise_for_status()
                rows = resp.json().get("data") or []
            except (requests.RequestException, ValueError) as exc:
                self._record_error(f"page offset={offset}: {exc}")
                break

            for row in rows:
                home = row.get("homeTeam") or {}
                away = row.get("awayTeam") or {}
                league = row.get("league") or {}
                country = row.get("country") or {}
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
                        competition=_highlightly_competition_name(league, country),
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
        else:
            # Every page came back full, so the day continues past the cap.
            # Said out loud rather than truncated silently: this provider
            # drives discovery, and a >500-fixture Saturday quietly missing
            # its tail would look exactly like a small slate.
            self._record_error(
                f"day has at least {_HIGHLIGHTLY_MAX_PAGES * _HIGHLIGHTLY_PAGE_SIZE} "
                f"fixtures; discovery stopped at the {_HIGHLIGHTLY_MAX_PAGES}-page cap "
                "and anything past it was never seen"
            )
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
        # First-leg scores, by first-leg event id. Both legs of a tie can
        # appear on one day's listing in a compressed cup round, and a
        # None entry is a cached answer too.
        self._previous_leg_cache: dict[str, tuple[str, str, int, int] | None] = {}
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

    def _previous_leg_score(
        self, row: dict, home_id: str, away_id: str
    ) -> dict[str, int | None]:
        """The first leg's score, mapped onto *tonight's* sides.

        One request per two-legged tie and none for anything else -- a slate
        has a handful of these. Cached per first-leg id because both legs of a
        tie can appear on one day's listing in a compressed cup round.

        The mapping is done here and not downstream because this is where both
        fixtures' team ids are in hand. The sides swap between legs, so a raw
        home/away pair carried forward would be read the wrong way round
        exactly half the time -- and the whole point of the field is to say
        which side is chasing.

        Any failure answers ``{}``: no first-leg score is the same state as no
        first leg, and a cup tie whose earlier leg cannot be read must not stop
        the fixture being discovered.
        """
        previous = row.get("previous_leg_event_id")
        if not previous:
            return {}
        key = str(previous)
        if key not in self._previous_leg_cache:
            self._previous_leg_cache[key] = self._fetch_previous_leg(key)
        leg = self._previous_leg_cache[key]
        if leg is None:
            return {}
        leg_home_id, leg_away_id, leg_home, leg_away = leg
        if leg_home_id == home_id and leg_away_id == away_id:
            return {
                "previous_leg_goals_home": leg_home,
                "previous_leg_goals_away": leg_away,
            }
        if leg_home_id == away_id and leg_away_id == home_id:
            return {
                "previous_leg_goals_home": leg_away,
                "previous_leg_goals_away": leg_home,
            }
        # The provider points at a fixture between different teams. That is not
        # a first leg however it is labelled, and guessing an orientation for it
        # would attach another tie's score to this one.
        return {}

    def _fetch_previous_leg(
        self, event_id: str
    ) -> tuple[str, str, int, int] | None:
        try:
            result = self._client.get_event_result(event_id)
        except Exception:  # noqa: BLE001 - a missing first leg is context, not a failure
            return None
        if result.status not in (
            SourceResultStatus.SUCCESS,
            SourceResultStatus.VALID_EMPTY,
        ):
            return None
        event = (result.value or {}).get("event") or {}
        score = event.get("score") or {}
        home = (event.get("home_team") or {}).get("provider_team_id")
        away = (event.get("away_team") or {}).get("provider_team_id")
        if home is None or away is None:
            return None
        if score.get("home") is None or score.get("away") is None:
            return None
        try:
            return (str(home), str(away), int(score["home"]), int(score["away"]))
        except (TypeError, ValueError):
            return None

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
                            # Stakes. These three were on every ``/events/``
                            # row all along -- ``_normalize_event_row`` has
                            # parsed them since 2026-08-31 -- and this dict was
                            # where they stopped: ``_to_event_record`` reads
                            # ``raw.get("round_name")`` and got None on 165 of
                            # 165 fixtures because nothing ever put it here.
                            # Verified live 2026-09-03: the listing answers
                            # ``"round_name": "Quarterfinals"`` and
                            # ``"previous_leg_event_id": 587786`` for the
                            # Grêmio-Internacional fixture whose dossier said
                            # null to both.
                            "round_name": row.get("round_name"),
                            "group_name": row.get("group_name"),
                            "previous_leg_event_id": row.get("previous_leg_event_id"),
                            **self._previous_leg_score(
                                row,
                                str(home["provider_team_id"]),
                                str(away["provider_team_id"]),
                            ),
                        },
                    )
                )

            total = (result.value or {}).get("total_count") or 0
            if len(matches) < _BZZOIRO_PAGE_SIZE or (page + 1) * _BZZOIRO_PAGE_SIZE >= total:
                break
        return events


# `.get(sport, ())`, not `[sport]`: --sports is free text with no argparse
# choices, and OddsAPIEventsAdapter also declares basketball and hockey.
#
# football: SlateGate rejects any event without a bzzoiro row regardless (297
# of 342 on 2026-09-04), so discovering it elsewhere first is pure noise in
# the artifact -- an event that cannot be enriched should not be discovered.
# tennis: odds-api is the only schedule source left after bzzoiro-tennis was
# removed (see discover_events' docstring) and highlightly's tennis discovery
# never carried a native id anything downstream could use.
DISCOVERY_SOURCES_BY_SPORT: dict[str, tuple[str, ...]] = {
    "football": ("bzzoiro",),
    "tennis": ("odds-api",),
}


def _fetch_source_events(source: AbstractSourceAdapter, date: str, sports: list[str]) -> list[DiscoveredEvent]:
    events: list[DiscoveredEvent] = []
    for sport in sports:
        if sport not in source.supported_sports:
            continue
        if source.name not in DISCOVERY_SOURCES_BY_SPORT.get(sport, ()):
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
        #
        # Gated on the source, not on referee_id being set: a fixture whose
        # referee has not been assigned yet used to lose the *whole* block --
        # including is_local_derby, weather and now round_name/group_name/
        # previous_leg_event_id -- even though none of those depend on a
        # referee at all. Verified live 2026-08-31: Sutton United - Wealdstone
        # carries "is_local_derby": true with "referee_id": null, and the old
        # gate would have silently dropped the derby flag along with it.
        # enrich.py's "referee: no referee_id" data_gap already reads
        # context.referee_id itself, not whether a context object exists, so
        # this does not change referee-coverage reporting at all.
        if src.source == "bzzoiro":
            fixture_context = FixtureContext(
                referee_id=raw.get("referee_id"),
                venue_id=raw.get("venue_id"),
                league_id=str(raw.get("league_id") or "") or None,
                is_local_derby=bool(raw.get("is_local_derby")),
                is_neutral_ground=bool(raw.get("is_neutral_ground")),
                travel_distance_km=raw.get("travel_distance_km"),
                weather=raw.get("weather"),
                round_name=raw.get("round_name"),
                group_name=raw.get("group_name"),
                previous_leg_event_id=(
                    str(raw["previous_leg_event_id"])
                    if raw.get("previous_leg_event_id") is not None
                    else None
                ),
                previous_leg_goals_home=raw.get("previous_leg_goals_home"),
                previous_leg_goals_away=raw.get("previous_leg_goals_away"),
                home_team_id=str(raw.get("home_team_id") or "") or None,
                away_team_id=str(raw.get("away_team_id") or "") or None,
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
    """Discover football/tennis events for ``date``, dedup them, and classify
    each merged fixture's identity confidence.

    All three source adapters (The Odds API, Highlightly, Bzzoiro) are always
    constructed -- ``source_errors`` reads the full list -- but
    ``DISCOVERY_SOURCES_BY_SPORT`` narrows which of them are actually queried
    per sport. Football discovers from bzzoiro only: SlateGate rejects every
    event without a bzzoiro identity regardless (section 4.1), so discovering
    one nowhere else can enrich is pure noise in the artifact. Tennis
    discovers from odds-api only, the sole schedule source left after the
    bzzoiro tennis adapter was removed on 2026-09-02 (it had been the only one
    handing over native tennis ids, and stopped answering -- HTTP 402, paid
    addon -- before that ever paid for itself); Highlightly's tennis
    discovery never carried a native id anything downstream could use either.
    ESPN and tennis-abstract both resolve a player from a name, so nothing
    downstream depends on a tennis discovery source's ids.

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
    ]
    events_by_source = _fetch_all_sources(sources, date, sports)
    source_errors = {
        src.name: list(src.last_errors) for src in sources if src.last_errors
    }
    _canonicalize_competition_names(events_by_source)
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
        source_errors=source_errors,
        degraded_reasons=_degraded_reasons(source_errors),
    )


def _degraded_reasons(source_errors: dict[str, list[str]]) -> list[str]:
    """Why this slate is smaller than the day, if it is.

    Only quota exhaustion on a slate-critical source counts. A source that
    404s one page or times out once has cost corroboration, which is a
    different and much smaller problem than a source that stops producing
    fixtures -- and a "degraded" label that fires on both is a label nobody
    reads.
    """
    reasons: list[str] = []
    for name in sorted(SLATE_CRITICAL_SOURCES):
        for message in source_errors.get(name, []):
            if "quota exhausted" in message:
                reasons.append(f"{name}: {message}")
    return reasons
