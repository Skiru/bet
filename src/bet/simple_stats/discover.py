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

from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture
from bet.discovery.sources.base import AbstractSourceAdapter
from bet.discovery.sources.odds_api import BASE_URL as ODDS_API_BASE_URL
from bet.discovery.sources.odds_api import OddsAPIAdapter

from bet.simple_stats.contracts import EventListV1, EventRecord

logger = logging.getLogger(__name__)

_AMBIGUOUS_WINDOW_SECONDS = 6 * 3600

# Highlightly's per-page cap on /matches; the endpoint pages via `offset`.
_HIGHLIGHTLY_PAGE_SIZE = 100
_HIGHLIGHTLY_MAX_PAGES = 5


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
    for src in fixture.sources:
        raw = src.raw_data if isinstance(src.raw_data, dict) else {}
        home_id = str(raw.get("home_team_id") or "")
        away_id = str(raw.get("away_team_id") or "")
        if home_id and away_id and home_id != away_id:
            provider_team_ids[src.source] = {"home": home_id, "away": away_id}

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
    """Discover football/tennis events for ``date`` from The Odds API and
    Highlightly, dedup them, and classify each merged fixture's identity
    confidence.

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
