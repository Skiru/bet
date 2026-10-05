"""SAMPLES — build one metric sample per priced market (PLAN §6.1).

Only metrics that Superbet actually prices are sampled (A5): a sample for a
market nobody quotes is a call we paid for and cannot bet.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.comparability import (
    FRIENDLIES_PATH,
    SAME_COMPETITION_METRICS,
    is_friendly_event,
    is_knockout,
    pick_same_competition,
)
from bet.sofa.comparability import FRIENDLY_COMPETITION_IDS as _FRIENDLY_IDS
from bet.sofa.config import SofaConfig, config_path
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    GapEntry,
    GapReason,
    MetricSample,
    Observation,
    PlayerSample,
    Readiness,
)
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.market_mapper import (
    classify_market,
    derived_base,
    derived_side_metric,
)
from bet.sofa.metrics import (
    FOOTBALL_METRICS,
    check_halves_identity,
    check_identities,
    extract_flat_statistics,
    extract_metric,
    infer_best_of,
    zero_pair_not_recorded,
)
from bet.sofa.players import (
    extract_player_metric,
    is_player_metric,
    match_player,
    player_sample_key,
    squad_statistics,
)
from bet.sofa.reserve_squads import (
    RESERVE_COMPETITIONS,
    TeamMatch,
    describe,
    reserve_event_ids,
)
from bet.sofa.schedule import fixture_schedule
from bet.sofa.settle import is_completed_event, surfaces_comparable
from bet.sofa.superbet import SuperbetClient, odds_items

# Metrics whose only source is /event/{id}/incidents.
INCIDENT_METRICS = frozenset({"cards_points_total", "cards_points_for"})


# The friendly list and its reader live in comparability (one predicate for
# every history reader, 2026-10-04); re-exported here for the old importers.
FRIENDLY_COMPETITION_IDS: frozenset[int] = _FRIENDLY_IDS
_FRIENDLIES_PATH = FRIENDLIES_PATH


def is_friendly_fixture(sport: str, competition_id: int | None) -> bool:
    """A football fixture played in an excluded competition (2026-10-01).

    The list kept friendlies out of the SAMPLES only, so a friendly could
    still be the fixture: 15 on 2026-10-01 (Club / U19 / U23 Friendly Games)
    carried 465 sheet rows and 16 VALUE rows, priced from league samples that
    describe a different game. COUPON and CONFIDENCE refuse them.
    """
    return (
        sport == "football"
        and competition_id is not None
        and competition_id in FRIENDLY_COMPETITION_IDS
    )

_NO_STATS_PATH = config_path("sofa_no_stats_tournaments.json")


def _load_no_stats_tournament_ids() -> frozenset[int]:
    """Tournaments for which /event/{id}/statistics has never answered 200.

    These are not on the board — they are the lower divisions, regional cups
    and friendlies that turn up in an *opponent's historical sample*, which is
    exactly where `board.load_excluded_tournament_ids` predicted they would be
    and why that list correctly ships empty. Measured on 2026-09-22 over one
    run's log: 3,806 of 26,493 live Sofascore requests were a 404 on this
    route, and 1,241 of them sat in tournaments that have never once served
    statistics across 35,815 cached events.

    Skipping is behaviourally identical to the 404 it replaces:
    ``extract_flat_statistics(None)`` returns ``{}`` either way, so the event
    contributes no observation. Nothing is defaulted to zero and nothing is
    written to the cache — a skip must not become a fact we claim to have
    measured.

    A missing or malformed config degrades to "skip nothing": the pipeline
    pays what it pays today, which is the safe direction.
    """
    try:
        raw = json.loads(_NO_STATS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    entries = raw.get("tournaments", []) if isinstance(raw, dict) else []
    ids: set[int] = set()
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), int):
            ids.add(entry["id"])
        elif isinstance(entry, int):
            ids.add(entry)
    return frozenset(ids)


NO_STATS_TOURNAMENT_IDS: frozenset[int] = _load_no_stats_tournament_ids()


def statistics_are_hopeless(event: dict[str, Any]) -> bool:
    """True when this event's tournament has never served statistics.

    The event's own payload wins over the list. ``hasEventPlayerStatistics``
    is True for 11,574 cached events and only 20 of those lacked statistics
    (0.2%), and it is True for *none* of the 1,241 events this list skips — so
    honouring it costs nothing today and is the valve that lets a tournament
    which starts publishing back in before the next fit.
    """
    if event.get("hasEventPlayerStatistics") is True:
        return False
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    return unique.get("id") in NO_STATS_TOURNAMENT_IDS


def metrics_from_offer(offer: FixtureOffer | None) -> set[str]:
    """Canonical metric names the pre-sample OFFER already found a price for.

    This is what makes the pre-sample OFFER a gate rather than a dead stage
    (F19). The A4 docstring claimed the offer was read twice "so we only pay
    for metrics somebody actually prices", but nothing read the artifact:
    SAMPLES built its own SuperbetClient and asked Superbet again, once per
    fixture, ~600 requests a day to re-learn what 04_offer.json already said.
    """
    if offer is None:
        return set()
    wanted: set[str] = set()
    for rung in offer.rungs:
        # F54. A player metric is not read from /statistics and has no
        # reading in `extract_metric`; asking for it there would return
        # STAT_KEY_ABSENT once per historical event per player and bury the
        # real gaps under thousands of invented ones.
        # `players_from_offer` collects these instead.
        if is_player_metric(rung.market):
            continue
        # A derived market is named for the question it asks
        # ("handicap_games"), not for the sample it needs
        # ("games_won_for"). Passing the market name through means SAMPLES
        # never builds the metric, SHEET then reports STAT_KEY_ABSENT, and the
        # whole family goes unpriced while looking like a provider gap. 863
        # tennis rungs were lost exactly this way on 2026-09-18 (F40).
        base = derived_base(rung.market)
        if base is not None:
            wanted.add(derived_side_metric(base))
            continue
        wanted.add(rung.market)
    return wanted


def players_from_offer(offer: FixtureOffer | None) -> dict[str, set[str]]:
    """``{metric: {player as Superbet writes him}}`` for the player rungs.

    The companion to `metrics_from_offer`, and separate from it for the same
    reason the family needed its own classifier: the subject is a person, not
    a side, and a fixture carries as many of them as Superbet chose to quote.

    Only what is priced (A5). A squad list is one request per historical
    event; paying it for players nobody offers a line on would be the whole
    squad's worth of calls for nothing.
    """
    wanted: dict[str, set[str]] = {}
    if offer is None:
        return wanted
    for rung in offer.rungs:
        if is_player_metric(rung.market) and rung.subject:
            wanted.setdefault(rung.market, set()).add(rung.subject)
    return wanted


def fetch_available_metrics(
    fixture: Fixture, superbet_client: SuperbetClient
) -> set[str]:
    """Ask Superbet directly which metrics it prices for this fixture.

    The fallback for a fixture the offer artifact does not cover. Prefer
    metrics_from_offer: it costs nothing.
    """
    available_metrics: set[str] = set()
    failures: list[str] = []
    for s_id in fixture.superbet_event_ids:
        # One listing's error is that listing's, as in OfferFetcher: Superbet
        # raises curl_cffi's HTTPError (not a ProviderError) on a removed
        # event, and escaping here it took the whole SAMPLES stage down after
        # every other fixture had finished (review 2026-10-01).
        try:
            payload = superbet_client.event_odds(s_id)
        except Exception as exc:  # noqa: BLE001 - one listing, not the stage
            failures.append(f"{s_id}: {type(exc).__name__}: {exc}")
            continue
        for item in odds_items(payload):
            classified = classify_market(item.get("marketName"))
            if classified:
                available_metrics.add(classified[0])
    # Every listing raised: Superbet gave no answer, which is not "nothing is
    # priced". Returning the empty set blocked the fixture NO_PRICE, which is
    # not a provider fault, so SAMPLES dropped its previous good sample
    # instead of carrying it over (review 2026-10-02). A ProviderError is
    # blocked PROVIDER_ERROR by process_fixture_samples - still one fixture,
    # never the stage.
    if fixture.superbet_event_ids and len(failures) == len(fixture.superbet_event_ids):
        raise ProviderError(
            "every Superbet listing failed: " + "; ".join(failures)[:500]
        )
    return available_metrics


def fixture_round_event(fixture: Fixture) -> dict[str, Any]:
    """The fixture's round as the event shape comparability.is_knockout reads
    (roundInfo and the stage name the Fixture keeps)."""
    return {
        "roundInfo": {
            "cupRoundType": fixture.cup_round_type,
            "name": fixture.round_name or "",
        },
        "tournament": {"name": fixture.competition_name},
    }


def _competition_id(event: dict[str, Any]) -> int | None:
    value = event.get("tournament", {}).get("uniqueTournament", {}).get("id")
    return int(value) if isinstance(value, int) else None


# Indexed events read per entity (listing_index.py): the reach of the five
# pages the walk below may read (~30 events each), with room for the events a
# surface or format filter refuses.
INDEXED_HISTORY_LIMIT = 200


def get_historical_events(
    client: SofascoreClient,
    cache: SofaCache,
    entity_id: int,
    sport: str,
    fixture: Fixture,
    config: SofaConfig,
    gaps: list[GapEntry] | None = None,
    pool_out: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The last ``sample_n`` finished events for ``entity_id`` before kickoff.

    The listing goes through the TTL cache: a second run of the same day must
    not re-fetch pages it already holds (E2/T13).

    ``pool_out``, when given (football), receives every admissible event the
    read pages and the listed-event index hold, newest first and through the
    same finish_history - the pool a goal sample is picked from
    (comparability.SAME_COMPETITION_METRICS). It costs no request: the pages
    are the ones this walk read and the index is local.
    """
    events: list[dict[str, Any]] = []
    page = 0
    # Reported once per entity, not once per rejected event.
    surface_unknown_reported = False
    # Ids of everything the pages listed, admitted or not, and each read
    # page's (newest, oldest) start - the time span it covers.
    page_ids: set[int] = set()
    spans: list[tuple[int, int]] = []

    def admit(event: dict[str, Any], report: bool = True) -> bool:
        """Whether one listed event may enter the sample (gaps say why not,
        unless ``report`` is False - the pool's second look at an event)."""
        nonlocal surface_unknown_reported
        # A walkover or retirement is `finished` but did not produce a
        # comparable result; it must not enter a sample (L31).
        if not is_completed_event(event):
            # L14: a gate nobody can see looks like missing data. An event
            # dropped because it never produced a comparable result is a
            # known reason, so say so instead of silently shortening the
            # sample.
            if gaps is not None and report:
                status = event.get("status", {}).get("type", "unknown")
                code = event.get("status", {}).get("code")
                # "status=finished" under a reason called NOT_FINISHED read
                # as a contradiction; it is a retirement or walkover.
                what = (
                    f"finished abnormally (status code {code}: retirement, "
                    "walkover or similar)"
                    if str(status).lower() == "finished"
                    else f"status={status}"
                )
                gaps.append(
                    GapEntry(
                        reason=GapReason.EVENT_NOT_FINISHED,
                        metric="all",
                        detail=(
                            f"event {event.get('id')} {what} "
                            f"excluded from entity {entity_id} sample"
                        ),
                    )
                )
            return False

        start_ts = event.get("startTimestamp")
        if not start_ts:
            return False
        # T12: an event at or after our kickoff is the future leaking in.
        if datetime.fromtimestamp(start_ts, UTC) >= fixture.kickoff_utc:
            return False

        # A friendly, a pre-season tournament or an exhibition describes a
        # different game in every sport (comparability, 2026-10-04: the
        # Torneio de Verao entered Chaves' sample as a league match).
        if is_friendly_event(event, sport):
            return False

        if sport == "tennis":
            # groundType IS on the listing (30/30 in the recorded payload);
            # a clay match does not describe a hard-court match (§5.7).
            #
            # When OUR fixture's surface is unknown the `!=` below is not
            # a surface filter at all — it keeps only past matches whose
            # surface is also unknown, which is almost none, and empties
            # the sample without saying why. That is the L14 failure the
            # block above exists to prevent, so it gets the same
            # treatment: refuse the comparison and record the reason.
            #
            # 2026-09-21, corrected after review: six fixtures had no
            # surface (all UTR Pro Tennis Tour Norfolk). Five were blocked
            # upstream for NO_PRICE, but 17132335 was PRICED and did reach
            # sampling — so the case is live, not hypothetical. It still
            # recorded no SURFACE_UNKNOWN that day, because
            # `is_completed_event` above rejected every candidate first
            # and the loop never got here. The guard is therefore correct
            # but UNPROVEN on live data: a fixture can still report
            # THIN_SAMPLE when the real reason is that its surface is
            # unknown.
            if fixture.ground_type is None:
                if gaps is not None and not surface_unknown_reported:
                    gaps.append(
                        GapEntry(
                            reason=GapReason.SURFACE_UNKNOWN,
                            metric="all",
                            detail=(
                                "fixture has no groundType; a sample "
                                "cannot be checked for surface "
                                "comparability"
                            ),
                        )
                    )
                    surface_unknown_reported = True
                return False
            if not surfaces_comparable(
                event.get("groundType"), fixture.ground_type
            ):
                return False
            # defaultPeriodCount is NOT on the listing, so the format is
            # derived from sets won. None means "cannot tell" — and an
            # unknown format is not a match for a known one.
            if fixture.default_period_count is not None:
                if infer_best_of(event) != fixture.default_period_count:
                    return False

        home_id = event.get("homeTeam", {}).get("id")
        away_id = event.get("awayTeam", {}).get("id")
        if home_id != entity_id and away_id != entity_id:
            return False

        return True

    fixture_competition: int | None = getattr(fixture, "competition_id", None)

    def usable(candidates: list[dict[str, Any]]) -> int:
        """Candidates that can enter the sample: one listing per match, and
        in football none a second squad played (reserve_squads)."""
        kept = one_listing_per_match(candidates)
        if sport == "football":
            reserve, _ = second_squad_matches(
                kept, fixture_competition, int(fixture.kickoff_utc.timestamp())
            )
            kept = [e for e in kept if e.get("id") not in reserve]
        return len(kept)

    while len(events) < config.sample_n and page < 5:
        cached = cache.get_entity_events(entity_id, "last", page)
        if cached is not None:
            payload: dict[str, Any] | None = cached
        else:
            fetched = client.entity_events(entity_id, "last", page)
            payload = fetched
            if fetched:
                cache.save_entity_events(entity_id, "last", page, fetched)

        page_events = (payload or {}).get("events") or []
        if not page_events:
            break

        for event in page_events:
            # No early break on len(events). Sofascore returns each page
            # **ascending** — oldest first — measured 296 of 296 cached page-0
            # listings. Taking the first `sample_n` therefore took the ten
            # *oldest* of the thirty most recent, which is how a player was
            # priced off matches from thirteen months earlier while three
            # matches from the same tournament that week sat unread in the
            # same payload (F46). The page is bounded at ~30 events, so
            # scanning all of it costs nothing; the recency cut happens once,
            # after the loop.
            if isinstance(event.get("id"), int):
                page_ids.add(event["id"])
            if admit(event):
                events.append(event)
        starts = [e["startTimestamp"] for e in page_events
                  if isinstance(e, dict) and isinstance(e.get("startTimestamp"), int)]
        if starts:
            spans.append((max(starts), min(starts)))

        # Pages go backwards in time (page 0 is the most recent block), so
        # another page can only add older matches. Stop as soon as this page
        # has produced enough candidates — the request count is unchanged
        # from before the fix.
        page += 1
        if usable(events) >= config.sample_n:
            break

    # The listed-event index (listing_index.py) holds matches that slid out of
    # every cached page when a newer page 0-2 was saved over the old ones.
    # Such a match lies strictly between page k's oldest start and page k+1's
    # newest (the shallower page was re-saved after it slid), or beyond the
    # deepest page read. An indexed event *inside* a read page's own span is
    # one Sofascore no longer lists there - removed, or re-listed under
    # another id - and the index never forgets, so it is not added (F4). Ids
    # the pages listed are never added either: a page inside its TTL is the
    # fresher copy. Beyond the deepest page only tops up a sample the pages
    # left short, without a request.
    #
    # No page read at all (page 0 neither cached nor served): the walk says
    # nothing about this entity's listing today, so the index does not stand
    # in for it - a sample built from the index alone would carry no gap and
    # look like a fresh read (F2). The gap says why the side is empty.
    # Empty index: nothing is added and the sample is what it always was.
    if not spans:
        if gaps is not None:
            gaps.append(
                GapEntry(
                    reason=GapReason.PROVIDER_ERROR,
                    metric="all",
                    detail=(
                        f"entity {entity_id}: listing page 0 unavailable "
                        "(not cached, no events served); the listed-event "
                        "index is not read without a page"
                    ),
                )
            )
    else:
        short = usable(events) < config.sample_n
        deepest_oldest = spans[-1][1]
        windows = [(older[0], newer[1])
                   for newer, older in zip(spans, spans[1:], strict=False)]
        for event in cache.get_listed_events(
            entity_id, "last", int(fixture.kickoff_utc.timestamp()),
            INDEXED_HISTORY_LIMIT,
        ):
            if event["id"] in page_ids:
                continue
            start = event.get("startTimestamp")
            if not isinstance(start, int):
                continue
            in_gap = any(lo < start < hi for lo, hi in windows)
            beyond = start < deepest_oldest
            if not (in_gap or (short and beyond)):
                continue
            page_ids.add(event["id"])
            if admit(event):
                events.append(event)

    if pool_out is not None and sport == "football" and spans:
        # Every admissible match the read pages and the index hold, under the
        # index rule above (an indexed event inside a read page's span is one
        # Sofascore no longer lists there), without the "short" condition.
        pool = list(events)
        pooled = {e.get("id") for e in pool}
        deepest_oldest = spans[-1][1]
        windows = [(older[0], newer[1])
                   for newer, older in zip(spans, spans[1:], strict=False)]
        for event in cache.get_listed_events(
            entity_id, "last", int(fixture.kickoff_utc.timestamp()),
            INDEXED_HISTORY_LIMIT,
        ):
            start = event.get("startTimestamp")
            if event.get("id") in pooled or not isinstance(start, int):
                continue
            listed_here = event.get("id") in page_ids
            in_gap = any(lo < start < hi for lo, hi in windows)
            if listed_here or not (in_gap or start < deepest_oldest):
                continue
            if admit(event, report=False):
                pool.append(event)
                pooled.add(event.get("id"))
        # cut_at_conflict: the pool reaches years back (five pages and the
        # index), so a two-squad clash long before the newest ten emptied the
        # whole pool and the goal sample fell back to the newest ten without
        # a word (2026-10-05: Eastbourne Borough - Sussex Senior Cup and
        # National League South on one day in February 2026; AS Nestos
        # Chrysoupolis - two matches 23.5 h apart in 2025). The pool keeps
        # the stretch after the newest clash instead; the cache replay the
        # curves are fitted on (calibrate_from_cache.recent_for) runs no
        # two-squad check on a history at all.
        pool_out.extend(
            finish_history(
                pool, entity_id, sport, fixture_competition,
                int(fixture.kickoff_utc.timestamp()), len(pool) + 1, None,
                cut_at_conflict=True,
            )
        )

    return finish_history(
        events, entity_id, sport, fixture_competition,
        int(fixture.kickoff_utc.timestamp()), config.sample_n, gaps,
    )


def finish_history(
    events: list[dict[str, Any]],
    entity_id: int,
    sport: str,
    fixture_competition: int | None,
    kickoff_ts: int,
    sample_n: int,
    gaps: list[GapEntry] | None = None,
    *,
    cut_at_conflict: bool = False,
) -> list[dict[str, Any]]:
    """The admitted events of one side, made into its sample.

    One listing per match; in football the second squad's matches out (or
    no sample at all when the fixture is the second squad's), one squad per
    entity; then the newest `sample_n`, newest first. Its own function so
    the cache replay (calibrate_from_cache, player markets) builds a side's
    history with exactly this code rather than a copy of it.

    ``cut_at_conflict`` (the goal-sample pool only): a two-squad clash keeps
    the matches after the newest clashing pair instead of emptying the side.
    The sample proper keeps the old rule - its candidates are the pages the
    walk read, so a clash there is a clash near the sample.
    """
    # The sample is the most recent `sample_n`, newest first.
    events = one_listing_per_match(events)
    if sport == "football":
        # Before one_squad_per_entity: a second squad's match a day from the
        # first team's is that guard's "two squads" too, and once the second
        # squad's matches are out the first team's listing is clean.
        reserve, fixture_is_reserve = second_squad_matches(
            events, fixture_competition, kickoff_ts
        )
        if fixture_is_reserve:
            if gaps is not None:
                gaps.append(
                    GapEntry(
                        reason=GapReason.RESERVE_SQUAD,
                        metric="all",
                        detail=(
                            f"entity {entity_id}: the fixture's competition "
                            f"{fixture_competition} is played by its second "
                            "squad under the first team's id; side left empty"
                        ),
                    )
                )
            return []
        if reserve:
            if gaps is not None:
                gaps.append(
                    GapEntry(
                        reason=GapReason.RESERVE_SQUAD,
                        metric="all",
                        detail=(
                            f"entity {entity_id}: matches its second squad "
                            "played under the first team's id excluded ("
                            + describe(_team_matches(events), reserve)
                            + ")"
                        ),
                    )
                )
            events = [e for e in events if e.get("id") not in reserve]
        events, conflict, after = _one_squad(events, entity_id)
        while conflict is not None and cut_at_conflict and after is not None:
            events, conflict, after = _one_squad(
                [e for e in events if int(e.get("startTimestamp") or 0) > after],
                entity_id,
            )
        if conflict is not None:
            if gaps is not None:
                gaps.append(
                    GapEntry(
                        reason=GapReason.ENTITY_CONFLICT,
                        metric="all",
                        detail=f"entity {entity_id}: {conflict}; side left empty",
                    )
                )
            return []
    events.sort(key=lambda e: e.get("startTimestamp") or 0, reverse=True)
    return events[:sample_n]


def _team_matches(events: list[dict[str, Any]]) -> list[TeamMatch]:
    out: list[TeamMatch] = []
    for e in events:
        eid, ts, comp = e.get("id"), e.get("startTimestamp"), _competition_id(e)
        if isinstance(eid, int) and isinstance(ts, int) and comp is not None:
            out.append(TeamMatch(eid, ts, comp))
    return out


def second_squad_matches(
    events: list[dict[str, Any]],
    competition_id: int | None,
    kickoff_ts: int,
    listed: Mapping[int, frozenset[int]] | None = None,
) -> tuple[frozenset[int], bool]:
    """(ids of the side's listed matches its second squad played, whether the
    fixture itself - ``competition_id`` at ``kickoff_ts`` - is the second
    squad's). The rule and its measurement: reserve_squads."""
    matches = _team_matches(events)
    probe = (kickoff_ts, competition_id) if competition_id is not None else None
    found = reserve_event_ids(
        matches, RESERVE_COMPETITIONS if listed is None else listed, probe
    )
    return found - {-1}, -1 in found


# No football side plays two matches inside a day. Two in an entity's listing
# mean one id carries two squads - or one match listed twice against an
# opponent filed under two ids, which one_listing_per_match cannot see.
MIN_HOURS_BETWEEN_MATCHES = 24
# The same result this close is one match re-listed even when the opponent's
# id and name both differ (Naft Masjed Soleyman 1-0 at 10:30 and at 11:30 on
# 2026-01-03, "Arka Alborz" and "Arka City FC").
RELISTED_WITHIN_HOURS = 3


def _goals_for_against(event: dict[str, Any], entity_id: int) -> tuple[Any, Any]:
    home, away = _score(event)
    if event.get("homeTeam", {}).get("id") == entity_id:
        return home, away
    return away, home


def _opponent(event: dict[str, Any], entity_id: int) -> tuple[Any, str]:
    other = (
        event.get("awayTeam", {})
        if event.get("homeTeam", {}).get("id") == entity_id
        else event.get("homeTeam", {})
    )
    return other.get("id"), str(other.get("name") or "").casefold()


def one_squad_per_entity(
    events: list[dict[str, Any]], entity_id: int
) -> tuple[list[dict[str, Any]], str | None]:
    """Collapse a re-listed match; name an entity that is two squads.

    Two matches of one side less than MIN_HOURS_BETWEEN_MATCHES apart are,
    measured on 2026-10-01's 111 football fixtures, one of three things:
    - one match re-listed: the same opponent and the same score a day apart
      (Hapoel Marmorek - FC Tzeirey Tira, 0-0 on 2026-01-09 10:45 and again
      on 01-10 10:00, a postponement kept twice), or the same kick-off and
      the same score against an opponent filed under two ids and two names
      (Hapoel Ironi Karmiel, 2026-09-04 11:45, "Hapoel Bnei Jat United" and
      "Hapoel Ihud Bnei Jatt F.C."), or the same score within
      RELISTED_WITHIN_HOURS - the (day, pair) key of
      one_listing_per_match sees neither. Kept once, the lowest id;
    - the same opponent with two different scores: nothing says which is the
      match, so neither stays (one_listing_per_match's rule);
    - anything else: two squads under one id - France / Slovenia / Türkiye /
      Switzerland / Poland U19 (two qualifiers a day, different opponents),
      Deportivo Santo Domingo 414281 (LigaPro Serie B and the amateur
      Ascenso Nacional, 19:00 and 21:30 on 2026-09-11). The side then has
      no sample, because its listing describes two teams.
    """
    kept, conflict, _ = _one_squad(events, entity_id)
    return kept, conflict


def _one_squad(
    events: list[dict[str, Any]], entity_id: int
) -> tuple[list[dict[str, Any]], str | None, int | None]:
    """one_squad_per_entity, plus on a clash the start of the later match of
    the first clashing pair (walking oldest first); None without a clash."""

    def start(e: dict[str, Any]) -> int:
        return int(e.get("startTimestamp") or 0)

    ordered = sorted(events, key=lambda e: (start(e), e.get("id") or 0))
    kept: list[dict[str, Any]] = []
    dropped: set[int] = set()
    for event in ordered:
        clash = next(
            (
                p
                for p in reversed(kept)
                if (start(event) - start(p)) / 3600 < MIN_HOURS_BETWEEN_MATCHES
            ),
            None,
        )
        if clash is None:
            kept.append(event)
            continue
        same_result = _goals_for_against(event, entity_id) == _goals_for_against(
            clash, entity_id
        )
        opp_a, opp_b = _opponent(event, entity_id), _opponent(clash, entity_id)
        same_opponent = (opp_a[0] is not None and opp_a[0] == opp_b[0]) or (
            bool(opp_a[1]) and opp_a[1] == opp_b[1]
        )
        close = (start(event) - start(clash)) / 3600 <= RELISTED_WITHIN_HOURS
        if same_result and (same_opponent or close):
            continue  # one match re-listed: the lower id stays
        if same_opponent:
            dropped.add(id(clash))  # two scores for one match: neither stays
            continue
        gap_h = (start(event) - start(clash)) / 3600
        return events, (
            f"events {clash.get('id')} and {event.get('id')} are {gap_h:.1f} h "
            "apart against different opponents - one id, two squads"
        ), start(event)
    return [e for e in kept if id(e) not in dropped], None, None


def _match_key(
    event: dict[str, Any], field: str
) -> tuple[str, frozenset[Any]] | None:
    start_ts = event.get("startTimestamp")
    home = event.get("homeTeam", {}).get(field)
    away = event.get("awayTeam", {}).get(field)
    if not start_ts or home is None or away is None:
        return None
    if field == "name":
        home, away = str(home).casefold(), str(away).casefold()
    day = datetime.fromtimestamp(start_ts, UTC).date().isoformat()
    return day, frozenset((home, away))


def _score(event: dict[str, Any]) -> tuple[Any, Any]:
    return (
        event.get("homeScore", {}).get("current"),
        event.get("awayScore", {}).get("current"),
    )


def one_listing_per_match(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per physical match: the same two sides on the same UTC day.

    Sofascore lists some matches twice under two event ids - same teams, same
    kick-off, same tournament, or a cup tie mirrored into a "friendly"
    tournament. Measured 2026-09-26/27: 16 of 1,280 and 12 of 970 sample
    sides carried such a pair (APS Zakynthos - APO Ellas Syrou, 17056234 and
    17079707; the Republika Srpska league; the Japan Regional League), and
    the sample counted the one match twice - a double weight on one result
    and a spread that looks tighter than it is.

    Copies that agree on the score collapse to the lowest event id. Copies
    that DISAGREE (FK Zlatibor Cajetina - Jedinstvo Putevi, 3-0 in the Kup
    OFS Uzice listing, 1-1 in the "Serbia Friendly Games" one, same
    timestamp) cannot both be the match and nothing says which is, so neither
    enters the sample.

    Matched on the two team ids, then on the two team names: the Japan
    Regional League lists one match in two tournaments under two different
    entity ids for the same club (Gakunan F Mosuperio, 16365146 and
    16189754, two hours apart on 2026-05-17), and only the names agree.
    """
    return _collapse(_collapse(events, "id"), "name")


def _collapse(events: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, frozenset[Any]], list[dict[str, Any]]] = {}
    keyless: list[dict[str, Any]] = []
    for event in events:
        key = _match_key(event, field)
        if key is None:
            keyless.append(event)
        else:
            groups.setdefault(key, []).append(event)
    kept = list(keyless)
    for copies in groups.values():
        if len({_score(e) for e in copies}) > 1:
            continue
        kept.append(min(copies, key=lambda e: e.get("id") or 0))
    return kept


def fetch_lineups(
    client: SofascoreClient, cache: SofaCache, event: dict[str, Any]
) -> dict[str, Any] | None:
    """Per-player statistics for one historical event, cached forever (F54).

    ``{}`` — asked, nothing there — is cached like any other answer, so a
    tournament that publishes no squads costs one request per event once and
    never again.
    """
    event_id = int(event["id"])
    cached = cache.get_event_lineups(event_id)
    if cached is not None:
        return cached or None
    fetched = client.event_lineups(event_id)
    payload = fetched if isinstance(fetched, dict) else None
    status_type = event.get("status", {}).get("type", "finished")
    if status_type in ("finished", "canceled", "abandoned"):
        cache.save_event_lineups(event_id, payload, status_type)
    return payload


def process_historical_event(
    client: SofascoreClient,
    cache: SofaCache,
    event: dict[str, Any],
    entity_id: int,
    sport: str,
    metrics_to_collect: set[str],
    fixture: Fixture,
    want_lineups: bool = False,
) -> dict[str, Any]:
    event_id = event["id"]

    # With the kick-off, an early cards-only snapshot is asked again once the
    # match is old enough for Sofascore to have filled it in (see cache.py).
    start = event.get("startTimestamp")
    cached_stats = cache.get_event_stats(
        event_id, kickoff_ts=int(start) if isinstance(start, (int, float)) else None
    )
    needs_incidents = sport == "football" and bool(
        metrics_to_collect & INCIDENT_METRICS
    )
    incidents_faulted = False
    if cached_stats:
        statistics_json, incidents_json, cached_status = cached_stats
        # NULL incidents mean "never asked", not "none": a match first cached
        # for a fixture with no card market has statistics and no incidents,
        # and every later card sample read it as NO_INCIDENTS without asking
        # (2026-10-01: 118 gaps over 59 events, all NULL). Ask once; a 404 is
        # stored as {} so it is a fact and is not paid for again.
        #
        # The ask is the only network call on this cached path, so a provider
        # fault here costs the card metrics only (NO_INCIDENTS), never the
        # match: escaping, it BLOCKED the whole fixture (review 2026-10-01).
        if incidents_json is None and needs_incidents:
            try:
                fetched = client.event_incidents(event_id)
            except (ProviderError, CircuitOpenError):
                fetched = None
                incidents_faulted = True
            else:
                cache.save_event_incidents(
                    event_id, fetched if fetched is not None else {}
                )
            incidents_json = fetched
    else:
        # A 404 we can predict from a payload we already hold. `/incidents` is
        # still asked for, though: 29 of these 1,241 events carry incidents
        # despite having no statistics, and card points have no other source —
        # so the saving stops at the route that was actually measured empty.
        # Not cached as a result either: we did not observe this one, and if
        # the list is ever wrong a later run must be free to ask.
        skipped_statistics = statistics_are_hopeless(event)
        statistics_json = (
            None if skipped_statistics else client.event_statistics(event_id)
        )
        incidents_json = None
        if needs_incidents:
            incidents_json = client.event_incidents(event_id)

        # A row whose statistics are NULL is read back as "asked, got 404", and
        # `get_event_stats` returning it stops the next run from asking at all.
        # A prediction must not be written into the cache wearing that costume:
        # if the list is ever wrong, the only thing that can correct it is a
        # later run still being free to ask.
        if not skipped_statistics or incidents_json is not None:
            status_type = event.get("status", {}).get("type", "finished")
            cache.save_event_stats(
                event_id, statistics_json, incidents_json, status_type
            )

    # {} is the stored fact "asked, got 404" - for every reader below it is
    # "no incidents". Read as a payload, check_identities saw zero goals on a
    # match with goals and marked EVERY metric INTERNAL_INCONSISTENT, for good
    # (review 2026-10-01).
    if not incidents_json:
        incidents_json = None
    flat_stats = extract_flat_statistics(statistics_json)
    ident_gap = check_identities(flat_stats, incidents_json, event, sport)
    # Reported, not blocking (PLAN §5.5, last row).
    halves_divergences = check_halves_identity(flat_stats)

    home_team = event.get("homeTeam", {})
    away_team = event.get("awayTeam", {})
    is_home = home_team.get("id") == entity_id
    opponent_name = (away_team if is_home else home_team).get("name") or "Unknown"

    match_dt = datetime.fromtimestamp(event["startTimestamp"], UTC)
    comp_id = _competition_id(event)
    season_id = event.get("season", {}).get("id")

    # Tennis is played on neutral ground; calling slot 1 "home" invents a fact (L7).
    venue: str | None = None if sport == "tennis" else ("home" if is_home else "away")

    collected: dict[str, Observation | GapReason] = {}
    # Why a 0-0 was refused, per metric, for the gap entry (2026-10-03).
    zero_notes: dict[str, str] = {}
    for metric in metrics_to_collect:
        if ident_gap:
            collected[metric] = ident_gap
            continue

        val = extract_metric(metric, sport, flat_stats, incidents_json, event, is_home)
        if incidents_faulted and metric in INCIDENT_METRICS:
            # Named as the provider fault it was, so SAMPLES' verdict sees it
            # (provider_fault_fixtures), not as a match without incidents.
            val = GapReason.PROVIDER_ERROR
        if isinstance(val, GapReason):
            collected[metric] = val
            if metric in INCIDENT_METRICS and val in (
                GapReason.ZERO_NOT_RECORDED,
                GapReason.CARDS_NOT_RECORDED,
            ):
                zero_notes[metric] = (
                    "incident list without a substitution or a yellow card:"
                    " no card record (metrics.cards_not_recorded)"
                )
            elif val is GapReason.ZERO_NOT_RECORDED:
                key = str(FOOTBALL_METRICS.get(metric, {}).get("sofascore", ""))
                note = zero_pair_not_recorded(key, flat_stats.get("ALL"))
                if note:
                    zero_notes[metric] = note
        else:
            collected[metric] = Observation(
                sofascore_event_id=event_id,
                match_date_utc=match_dt,
                opponent=opponent_name,
                value=val,
                competition_id=comp_id,
                season_id=season_id,
                venue=venue,  # type: ignore[arg-type]
            )

    home_id = home_team.get("id")
    away_id = away_team.get("id")
    is_h2h = {home_id, away_id} == {fixture.home_entity_id, fixture.away_entity_id}

    # F54. One squad list per event serves every player Superbet quotes on
    # this side. Only fetched when a player market asked for it, so a day
    # with no player rungs pays nothing.
    squad: dict[str, dict[str, Any]] | None = None
    if want_lineups:
        squad = squad_statistics(
            fetch_lineups(client, cache, event),
            is_home=is_home,
            statistics=statistics_json,
        )

    return {
        "event_id": event_id,
        "collected": collected,
        "is_h2h": is_h2h,
        "halves_divergences": halves_divergences,
        "zero_notes": zero_notes,
        "squad": squad,
        "match_date_utc": match_dt,
        "opponent": opponent_name,
        "competition_id": comp_id,
        "season_id": season_id,
        "venue": venue,
    }


def cached_listing(
    cache: SofaCache, entity_id: int, kickoff_ts: int
) -> list[dict[str, Any]]:
    """Every listed event of one side the cache holds - the 'last' pages the
    walk read and the listed-event index - whatever its status, one per id.
    No request (bet.sofa.schedule reads postponed events from it)."""
    seen: dict[Any, dict[str, Any]] = {}
    for page in range(5):
        payload = cache.get_entity_events(entity_id, "last", page)
        if not payload:
            break
        for event in payload.get("events") or []:
            if isinstance(event, dict) and event.get("id") is not None:
                seen.setdefault(event["id"], event)
    for event in cache.get_listed_events(
        entity_id, "last", kickoff_ts, INDEXED_HISTORY_LIMIT
    ):
        seen.setdefault(event.get("id"), event)
    return list(seen.values())


def goal_observations(
    client: SofascoreClient,
    cache: SofaCache,
    event: dict[str, Any],
    entity_id: int,
    metrics: set[str],
    fixture: Fixture,
) -> dict[str, Any]:
    """process_historical_event for goal metrics only, and never a request.

    A goal count is read from the listing (homeScore / awayScore), so a match
    picked into a goal sample needs no statistics. With statistics cached the
    usual path runs (its identity check included) - goal metrics alone ask
    for no incidents, so it makes no call. Without them the listing is read
    directly; the identity check, which compares the listing with the
    statistics, has nothing to compare.
    """
    start = event.get("startTimestamp")
    if cache.get_event_stats(
        event["id"], kickoff_ts=int(start) if isinstance(start, (int, float)) else None
    ) is not None:
        return process_historical_event(
            client, cache, event, entity_id, "football", metrics, fixture
        )
    home_team = event.get("homeTeam", {})
    away_team = event.get("awayTeam", {})
    is_home = home_team.get("id") == entity_id
    collected: dict[str, Observation | GapReason] = {}
    for metric in metrics:
        val = extract_metric(metric, "football", {}, None, event, is_home)
        if isinstance(val, GapReason):
            collected[metric] = val
        else:
            collected[metric] = Observation(
                sofascore_event_id=int(event["id"]),
                match_date_utc=datetime.fromtimestamp(event["startTimestamp"], UTC),
                opponent=(away_team if is_home else home_team).get("name") or "Unknown",
                value=val,
                competition_id=_competition_id(event),
                season_id=event.get("season", {}).get("id"),
                venue="home" if is_home else "away",
            )
    return {
        "event_id": event["id"],
        "collected": collected,
        "is_h2h": {home_team.get("id"), away_team.get("id")}
        == {fixture.home_entity_id, fixture.away_entity_id},
        "zero_notes": {},
    }


def build_player_samples(
    wanted: dict[str, set[str]],
    side_results: dict[str, list[dict[str, Any]]],
    gaps: list[GapEntry],
) -> dict[str, PlayerSample]:
    """One sample per (player metric, player Superbet quoted) — F54.

    `side_results` is ``{"side_a": [...], "side_b": [...]}`` of
    `process_historical_event` results, each carrying that side's squad for
    that match.

    The player is matched **per match**, against that match's squad, not once
    against a current roster. Squads change between a sample's oldest match
    and its newest, and a name matched once and then assumed would follow a
    departed player's number onto his replacement.

    Which side he belongs to is decided by where he was found more often, and
    a tie is refused rather than broken: a name that matches in both squads is
    two different people or one we cannot place, and pricing a shots line
    against the wrong squad is the F31 defect with a smaller subject.
    """
    samples: dict[str, PlayerSample] = {}
    for metric, players in sorted(wanted.items()):
        for player in sorted(players):
            per_side: dict[str, list[Observation]] = {"side_a": [], "side_b": []}
            per_side_matched: dict[str, str] = {}
            squad_matches = 0

            for side, results in side_results.items():
                for res in results:
                    squad = res.get("squad")
                    if not squad:
                        continue
                    if side == "side_a":
                        squad_matches += 1
                    matched = match_player(player, squad)
                    if matched is None:
                        continue
                    per_side_matched.setdefault(side, matched)
                    value = extract_player_metric(metric, squad[matched])
                    if isinstance(value, GapReason):
                        # EVENT_NOT_FINISHED here means "named in the squad,
                        # never came on" — the normal case, and not worth a
                        # gap entry per player per match. Everything else is.
                        if value is not GapReason.EVENT_NOT_FINISHED:
                            gaps.append(
                                GapEntry(
                                    reason=value,
                                    metric=metric,
                                    detail=(
                                        f"player {player!r} event "
                                        f"{res['event_id']} gap"
                                    ),
                                )
                            )
                        continue
                    per_side[side].append(
                        Observation(
                            sofascore_event_id=res["event_id"],
                            match_date_utc=res["match_date_utc"],
                            opponent=res["opponent"],
                            value=value,
                            minutes=squad[matched].get("minutesPlayed"),
                            competition_id=res["competition_id"],
                            season_id=res["season_id"],
                            venue=res["venue"],
                        )
                    )

            n_a, n_b = len(per_side["side_a"]), len(per_side["side_b"])
            if n_a == 0 and n_b == 0:
                gaps.append(
                    GapEntry(
                        reason=GapReason.NO_ENTITY_FOUND,
                        metric=metric,
                        detail=f"player {player!r} matched no squad member",
                    )
                )
                continue
            if n_a == n_b:
                gaps.append(
                    GapEntry(
                        reason=GapReason.AMBIGUOUS_ENTITY,
                        metric=metric,
                        detail=(
                            f"player {player!r} matched both squads equally "
                            f"({n_a} each); refusing to guess the side"
                        ),
                    )
                )
                continue
            side = "side_a" if n_a > n_b else "side_b"
            observations = sorted(
                per_side[side], key=lambda o: o.match_date_utc, reverse=True
            )
            samples[player_sample_key(metric, player)] = PlayerSample(
                metric=metric,
                player=player,
                matched_name=per_side_matched[side],
                side=side,  # type: ignore[arg-type]
                squad_matches=squad_matches
                if side == "side_a"
                else sum(1 for r in side_results["side_b"] if r.get("squad")),
                observations=observations,
            )
    return samples


def compute_readiness(
    metric_samples: dict[str, MetricSample], min_sample: int
) -> tuple[Readiness, dict[str, Readiness]]:
    """Readiness per metric, and the fixture's readiness as its best metric.

    §3.3 defines readiness on a metric. Reporting the fixture's *best* metric as
    the headline is only honest alongside the per-metric map, which is why both
    are returned and both are written to the run summary.
    """
    per_metric: dict[str, Readiness] = {}
    for name, sample in metric_samples.items():
        n_a = len(sample.side_a)
        n_b = len(sample.side_b)
        if n_a >= min_sample and n_b >= min_sample:
            per_metric[name] = "READY"
        elif n_a >= 1 or n_b >= 1:
            per_metric[name] = "PARTIAL"
        else:
            per_metric[name] = "BLOCKED"

    if not per_metric:
        return "BLOCKED", per_metric
    if "READY" in per_metric.values():
        return "READY", per_metric
    if "PARTIAL" in per_metric.values():
        return "PARTIAL", per_metric
    return "BLOCKED", per_metric


def process_fixture_samples(
    fixture: Fixture,
    client: SofascoreClient,
    cache: SofaCache,
    superbet_client: SuperbetClient,
    config: SofaConfig,
    offer: FixtureOffer | None = None,
) -> FixtureSamples:
    """Sample one fixture. A provider failure blocks this fixture, not the day.

    An exception escaping here takes down the whole slate over one bad fixture,
    and the operator is left with no artifact at all rather than an artifact
    that names the fixture that failed. The circuit breaker is the mechanism
    that stops a genuinely dead provider; a single error is not that.
    """
    try:
        return _process_fixture_samples(
            fixture, client, cache, superbet_client, config, offer
        )
    except CircuitOpenError as exc:
        return _blocked(fixture, GapReason.CIRCUIT_OPEN, str(exc))
    except ProviderError as exc:
        return _blocked(fixture, GapReason.PROVIDER_ERROR, str(exc))


def _blocked(fixture: Fixture, reason: GapReason, detail: str) -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=fixture.sofascore_event_id,
        readiness="BLOCKED",
        metrics={},
        gaps=[GapEntry(reason=reason, metric="all", detail=detail)],
    )


def _process_fixture_samples(
    fixture: Fixture,
    client: SofascoreClient,
    cache: SofaCache,
    superbet_client: SuperbetClient,
    config: SofaConfig,
    offer: FixtureOffer | None = None,
) -> FixtureSamples:
    # The offer artifact if the pre-sample OFFER covered this fixture, and only
    # otherwise a live call. This is the saving A4 always claimed (F19).
    #
    # An offer entry that names NO market is not that saving, though: it is the
    # absence of an answer, and it is only a fact about the moment it was
    # fetched. On 2026-09-21 the morning OFFER (08:05Z) found eight fixtures
    # unpriced, Superbet posted their ladders during the day, and the evening
    # SAMPLES read the stale emptiness and blocked all eight with "No priced
    # markets on Superbet" — 116 rungs, every fixture still hours from
    # kickoff, and not one Superbet request made to check. Same shape as F17:
    # remembering "nothing here" for too long buys requests with a silent hole.
    # So an empty entry falls through to the live call exactly like a missing
    # one; only a live call may conclude NO_PRICE.
    metrics_to_collect: set[str] = set()
    wanted_players: dict[str, set[str]] = {}
    if offer is not None:
        metrics_to_collect = metrics_from_offer(offer)
        wanted_players = players_from_offer(offer)
    if not metrics_to_collect and not wanted_players:
        metrics_to_collect = fetch_available_metrics(fixture, superbet_client)

    # F54. A squad list is only ever fetched for football, and only when the
    # offer already carries a player rung for this fixture. On 2026-09-22 that
    # was 4 of 182 football fixtures, so the whole family costs ~80 extra
    # requests a day rather than the ~3,600 an unconditional fetch would.
    want_lineups = fixture.sport == "football" and bool(wanted_players)

    if not metrics_to_collect and not wanted_players:
        return FixtureSamples(
            sofascore_event_id=fixture.sofascore_event_id,
            readiness="BLOCKED",
            metrics={},
            gaps=[
                GapEntry(
                    reason=GapReason.NO_PRICE,
                    metric="all",
                    detail="No priced markets on Superbet",
                )
            ],
        )

    sample_gaps: list[GapEntry] = []
    pool_a: list[dict[str, Any]] = []
    pool_b: list[dict[str, Any]] = []
    side_a_events = get_historical_events(
        client,
        cache,
        fixture.home_entity_id,
        fixture.sport,
        fixture,
        config,
        sample_gaps,
        pool_a,
    )
    side_b_events = get_historical_events(
        client,
        cache,
        fixture.away_entity_id,
        fixture.sport,
        fixture,
        config,
        sample_gaps,
        pool_b,
    )

    side_a_results = [
        process_historical_event(
            client,
            cache,
            e,
            fixture.home_entity_id,
            fixture.sport,
            metrics_to_collect,
            fixture,
            want_lineups,
        )
        for e in side_a_events
    ]
    side_b_results = [
        process_historical_event(
            client,
            cache,
            e,
            fixture.away_entity_id,
            fixture.sport,
            metrics_to_collect,
            fixture,
            want_lineups,
        )
        for e in side_b_events
    ]

    # The goal markets' own sample (comparability.SAME_COMPETITION_METRICS):
    # the side's newest REGULAR matches of the fixture's competition, when it
    # has at least SAME_COMPETITION_MIN of them; otherwise the sample above.
    goal_metrics = metrics_to_collect & SAME_COMPETITION_METRICS
    goal_results: dict[str, list[dict[str, Any]] | None] = {
        "Side A": None, "Side B": None,
    }
    # League fixtures only (review 2026-10-04): the rule was measured on
    # REGULAR targets; on 24,777 KNOCKOUT ones (cup rounds, play-offs) it made
    # goals_total worse by +0.00546 [+0.00373; +0.00725] and goals_for by
    # +0.01227 [+0.00951; +0.01526] (data/analysis_2026-10-04_night/
    # composition_knockout.md), reaching back to a tournament's group stage
    # years ago (China U23, Asian Games 2014). A knockout fixture keeps the
    # usual newest-ten sample.
    if (
        fixture.sport == "football"
        and goal_metrics
        and not is_knockout(fixture_round_event(fixture))
    ):
        for label, pool, entity in (
            ("Side A", pool_a, fixture.home_entity_id),
            ("Side B", pool_b, fixture.away_entity_id),
        ):
            picked = pick_same_competition(
                pool, fixture.competition_id, config.sample_n,
                _competition_id, lambda e: not is_knockout(e),
            )
            if picked is None:
                continue
            goal_results[label] = [
                goal_observations(client, cache, e, entity, goal_metrics, fixture)
                for e in picked
            ]

    metric_samples: dict[str, MetricSample] = {}
    gaps: list[GapEntry] = list(sample_gaps)

    for metric in sorted(metrics_to_collect):
        obs_a: list[Observation] = []
        obs_b: list[Observation] = []
        obs_h2h: list[Observation] = []
        h2h_event_ids: set[int] = set()

        for results, bucket, side_label in (
            (side_a_results, obs_a, "Side A"),
            (side_b_results, obs_b, "Side B"),
        ):
            if metric in goal_metrics and goal_results[side_label] is not None:
                results = goal_results[side_label] or []
            seen_in_side: set[int] = set()
            for res in results:
                val = res["collected"].get(metric)
                if isinstance(val, GapReason):
                    detail = f"{side_label} event {res['event_id']} gap"
                    note = (res.get("zero_notes") or {}).get(metric)
                    if note:
                        detail = f"{detail}: {note}"
                    gaps.append(GapEntry(reason=val, metric=metric, detail=detail))
                    continue
                if val is None:
                    continue
                # L13: one historical event contributes one observation per side.
                if val.sofascore_event_id in seen_in_side:
                    continue
                seen_in_side.add(val.sofascore_event_id)
                bucket.append(val)

                # A head-to-head match appears in both histories; it must enter
                # the h2h bucket once, not twice.
                if res["is_h2h"] and val.sofascore_event_id not in h2h_event_ids:
                    h2h_event_ids.add(val.sofascore_event_id)
                    obs_h2h.append(val)

        metric_samples[metric] = MetricSample(
            metric=metric, side_a=obs_a, side_b=obs_b, h2h=obs_h2h
        )

    player_samples: dict[str, PlayerSample] = {}
    if want_lineups:
        player_samples = build_player_samples(
            wanted_players,
            {"side_a": side_a_results, "side_b": side_b_results},
            gaps,
        )
        for key, sample in sorted(player_samples.items()):
            if len(sample.observations) < config.min_sample:
                gaps.append(
                    GapEntry(
                        reason=GapReason.THIN_SAMPLE,
                        metric=sample.metric,
                        detail=(
                            f"player {sample.player!r} appeared in "
                            f"{len(sample.observations)} of "
                            f"{sample.squad_matches} sampled matches, below "
                            f"min_sample={config.min_sample} ({key})"
                        ),
                    )
                )

    readiness, per_metric = compute_readiness(metric_samples, config.min_sample)
    for name, state in sorted(per_metric.items()):
        if state == "BLOCKED":
            gaps.append(
                GapEntry(
                    reason=GapReason.THIN_SAMPLE,
                    metric=name,
                    detail="no observation on either side",
                )
            )
        elif state == "PARTIAL":
            gaps.append(
                GapEntry(
                    reason=GapReason.THIN_SAMPLE,
                    metric=name,
                    detail=(
                        f"side_a={len(metric_samples[name].side_a)} "
                        f"side_b={len(metric_samples[name].side_b)} "
                        f"below min_sample={config.min_sample}"
                    ),
                )
            )

    # A fixture whose only priced family is a player market has no team
    # metric and would otherwise report BLOCKED with a full sample behind it.
    if not metric_samples and player_samples:
        readiness = (
            "READY"
            if any(
                len(sample.observations) >= config.min_sample
                for sample in player_samples.values()
            )
            else "PARTIAL"
        )

    kickoff_ts = int(fixture.kickoff_utc.timestamp())
    schedule = fixture_schedule(
        cached_listing(cache, fixture.home_entity_id, kickoff_ts),
        cached_listing(cache, fixture.away_entity_id, kickoff_ts),
        fixture.home_entity_id,
        fixture.away_entity_id,
        fixture.competition_id,
        kickoff_ts,
        fixture.sofascore_event_id,
        fixture.sport,
        fixture.season_id,
        fixture.category_name,
    )
    return FixtureSamples(
        sofascore_event_id=fixture.sofascore_event_id,
        readiness=readiness,
        metrics=metric_samples,
        gaps=gaps,
        players=player_samples,
        schedule=schedule,
    )
