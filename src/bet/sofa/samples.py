"""SAMPLES — build one metric sample per priced market (PLAN §6.1).

Only metrics that Superbet actually prices are sampled (A5): a sample for a
market nobody quotes is a call we paid for and cannot bet.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    GapEntry,
    GapReason,
    MetricSample,
    Observation,
    Readiness,
)
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.market_mapper import (
    classify_market,
    derived_base,
    derived_side_metric,
)
from bet.sofa.metrics import (
    check_halves_identity,
    check_identities,
    extract_flat_statistics,
    extract_metric,
    infer_best_of,
)
from bet.sofa.settle import is_completed_event
from bet.sofa.superbet import SuperbetClient, odds_items

_FRIENDLIES_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "sofa_friendly_competitions.json"
)

# Metrics whose only source is /event/{id}/incidents.
INCIDENT_METRICS = frozenset({"cards_points_total", "cards_points_for"})


def _load_friendly_ids() -> frozenset[int]:
    """Competition ids excluded from football counting samples (PLAN §6.1).

    A missing or malformed config degrades to "exclude nothing" rather than
    crashing — but the caller reports the size of this set, so an empty filter
    is visible in the run summary instead of being silently inert.
    """
    try:
        raw = json.loads(_FRIENDLIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    entries = raw.get("excluded", []) if isinstance(raw, dict) else []
    ids: set[int] = set()
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("competition_id"), int):
            ids.add(entry["competition_id"])
        elif isinstance(entry, int):
            ids.add(entry)
    return frozenset(ids)


FRIENDLY_COMPETITION_IDS: frozenset[int] = _load_friendly_ids()


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


def fetch_available_metrics(
    fixture: Fixture, superbet_client: SuperbetClient
) -> set[str]:
    """Ask Superbet directly which metrics it prices for this fixture.

    The fallback for a fixture the offer artifact does not cover. Prefer
    metrics_from_offer: it costs nothing.
    """
    available_metrics: set[str] = set()
    for s_id in fixture.superbet_event_ids:
        for item in odds_items(superbet_client.event_odds(s_id)):
            classified = classify_market(item.get("marketName"))
            if classified:
                available_metrics.add(classified[0])
    return available_metrics


def _competition_id(event: dict[str, Any]) -> int | None:
    value = event.get("tournament", {}).get("uniqueTournament", {}).get("id")
    return int(value) if isinstance(value, int) else None


def get_historical_events(
    client: SofascoreClient,
    cache: SofaCache,
    entity_id: int,
    sport: str,
    fixture: Fixture,
    config: SofaConfig,
    gaps: list[GapEntry] | None = None,
) -> list[dict[str, Any]]:
    """The last ``sample_n`` finished events for ``entity_id`` before kickoff.

    The listing goes through the TTL cache: a second run of the same day must
    not re-fetch pages it already holds (E2/T13).
    """
    events: list[dict[str, Any]] = []
    page = 0
    # Reported once per entity, not once per rejected event.
    surface_unknown_reported = False
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

            # A walkover or retirement is `finished` but did not produce a
            # comparable result; it must not enter a sample (L31).
            if not is_completed_event(event):
                # L14: a gate nobody can see looks like missing data. An event
                # dropped because it never produced a comparable result is a
                # known reason, so say so instead of silently shortening the
                # sample.
                if gaps is not None:
                    status = event.get("status", {}).get("type", "unknown")
                    gaps.append(
                        GapEntry(
                            reason=GapReason.EVENT_NOT_FINISHED,
                            metric="all",
                            detail=(
                                f"event {event.get('id')} status={status} "
                                f"excluded from entity {entity_id} sample"
                            ),
                        )
                    )
                continue

            start_ts = event.get("startTimestamp")
            if not start_ts:
                continue
            # T12: an event at or after our kickoff is the future leaking in.
            if datetime.fromtimestamp(start_ts, UTC) >= fixture.kickoff_utc:
                continue

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
                    continue
                if event.get("groundType") != fixture.ground_type:
                    continue
                # defaultPeriodCount is NOT on the listing, so the format is
                # derived from sets won. None means "cannot tell" — and an
                # unknown format is not a match for a known one.
                if fixture.default_period_count is not None:
                    if infer_best_of(event) != fixture.default_period_count:
                        continue
            else:
                comp_id = _competition_id(event)
                if comp_id is not None and comp_id in FRIENDLY_COMPETITION_IDS:
                    continue

            home_id = event.get("homeTeam", {}).get("id")
            away_id = event.get("awayTeam", {}).get("id")
            if home_id != entity_id and away_id != entity_id:
                continue

            events.append(event)

        # Pages go backwards in time (page 0 is the most recent block), so
        # another page can only add older matches. Stop as soon as this page
        # has produced enough candidates — the request count is unchanged
        # from before the fix.
        page += 1
        if len(events) >= config.sample_n:
            break

    # The sample is the most recent `sample_n`, newest first.
    events.sort(key=lambda e: e.get("startTimestamp") or 0, reverse=True)
    return events[: config.sample_n]


def process_historical_event(
    client: SofascoreClient,
    cache: SofaCache,
    event: dict[str, Any],
    entity_id: int,
    sport: str,
    metrics_to_collect: set[str],
    fixture: Fixture,
) -> dict[str, Any]:
    event_id = event["id"]

    cached_stats = cache.get_event_stats(event_id)
    if cached_stats:
        statistics_json, incidents_json, _ = cached_stats
    else:
        statistics_json = client.event_statistics(event_id)
        incidents_json = None
        needs_incidents = sport == "football" and bool(
            metrics_to_collect & INCIDENT_METRICS
        )
        if needs_incidents:
            incidents_json = client.event_incidents(event_id)

        status_type = event.get("status", {}).get("type", "finished")
        cache.save_event_stats(event_id, statistics_json, incidents_json, status_type)

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
    for metric in metrics_to_collect:
        if ident_gap:
            collected[metric] = ident_gap
            continue

        val = extract_metric(metric, sport, flat_stats, incidents_json, event, is_home)
        if isinstance(val, GapReason):
            collected[metric] = val
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

    return {
        "event_id": event_id,
        "collected": collected,
        "is_h2h": is_h2h,
        "halves_divergences": halves_divergences,
    }


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
    if offer is not None:
        metrics_to_collect = metrics_from_offer(offer)
    if not metrics_to_collect:
        metrics_to_collect = fetch_available_metrics(fixture, superbet_client)

    if not metrics_to_collect:
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
    side_a_events = get_historical_events(
        client,
        cache,
        fixture.home_entity_id,
        fixture.sport,
        fixture,
        config,
        sample_gaps,
    )
    side_b_events = get_historical_events(
        client,
        cache,
        fixture.away_entity_id,
        fixture.sport,
        fixture,
        config,
        sample_gaps,
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
        )
        for e in side_b_events
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
            seen_in_side: set[int] = set()
            for res in results:
                val = res["collected"].get(metric)
                if isinstance(val, GapReason):
                    gaps.append(
                        GapEntry(
                            reason=val,
                            metric=metric,
                            detail=f"{side_label} event {res['event_id']} gap",
                        )
                    )
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

    return FixtureSamples(
        sofascore_event_id=fixture.sofascore_event_id,
        readiness=readiness,
        metrics=metric_samples,
        gaps=gaps,
    )
