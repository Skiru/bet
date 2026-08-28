"""ENRICH: fetch raw statistics for every discovered event from all applicable
providers, combining (never falling back) across providers.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 1). (event, provider)
is one unit of work in ThreadPoolExecutor(max_workers=4), mirroring
src/bet/discovery/coordinator.py:_fetch_all_sources's ThreadPoolExecutor
idiom. Every task is wrapped so any exception (including SportDBMCPError and
subclasses) becomes a data_gaps entry, never an aborted run.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from bet.api_clients.rate_limiter import RateLimiter

from bet.simple_stats.contracts import (
    PRIORITY_METRICS,
    EventDossierListV1,
    EventDossierV1,
    EventListV1,
    EventRecord,
    MetricObservation,
    PlayerMetricObservation,
    Sport,
)
from bet.simple_stats.providers import (
    NATIVE_ID_PROVIDERS_BY_SPORT,
    PROVIDERS_BY_SPORT,
    FetchOutcome,
    RunBudget,
    fetch_bzzoiro_history,
    fetch_bzzoiro_lineup,
    fetch_bzzoiro_match_context,
    fetch_bzzoiro_player_history,
    fetch_bzzoiro_tennis_history,
    fetch_highlightly_history,
    fetch_provider_h2h_metrics,
    fetch_provider_team_metrics,
    fetch_sportdb_history,
)

MAX_WORKERS = 4

# Goalkeepers are skipped when collecting player props: none of the five prop
# markets in PLAYER_PROP_LINES is offered on a keeper, so asking for their
# history spends two calls an event to produce rows no coupon can use.
_SKIPPED_PROP_POSITIONS = frozenset({"G"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _side_names(event: EventRecord) -> tuple[str, str]:
    if event.sport == "tennis":
        return event.player_one or "", event.player_two or ""
    return event.home_team or "", event.away_team or ""


@dataclass(frozen=True)
class _Task:
    event: EventRecord
    slot: str  # "team_a" | "team_b" | "h2h"
    provider: str


def _season_label(event: EventRecord) -> str:
    """Flashscore season label for the event's kickoff, e.g. "2025-2026".
    European league seasons roll over in July, so a January fixture belongs to
    the season that started the previous calendar year."""
    year = int(event.start_time[:4]) if event.start_time[:4].isdigit() else datetime.now(timezone.utc).year
    month = int(event.start_time[5:7]) if event.start_time[5:7].isdigit() else 1
    start = year if month >= 7 else year - 1
    return f"{start}-{start + 1}"


def _run_task(task: _Task, rate_limiter: RateLimiter, run_budget: RunBudget) -> FetchOutcome:
    team_a, team_b = _side_names(task.event)

    if task.provider == "highlightly":
        ids = task.event.provider_team_ids.get("highlightly", {})
        home_id, away_id = ids.get("home", ""), ids.get("away", "")
        if task.slot == "team_a":
            return fetch_highlightly_history(home_id, away_id, rate_limiter, run_budget, mode="l10")
        if task.slot == "team_b":
            return fetch_highlightly_history(away_id, home_id, rate_limiter, run_budget, mode="l10")
        return fetch_highlightly_history(home_id, away_id, rate_limiter, run_budget, mode="h2h")

    if task.provider == "bzzoiro":
        ids = task.event.provider_team_ids.get("bzzoiro", {})
        home_id, away_id = ids.get("home", ""), ids.get("away", "")
        # H2H needs the fixture's own provider id, not a team pair: the meeting
        # history is embedded in /events/{id}/ and costs no listing call.
        bzz_event_id = task.event.source_ids.get("bzzoiro", "")
        as_of = task.event.start_time[:10]
        if task.slot == "team_a":
            return fetch_bzzoiro_history(
                home_id, away_id, rate_limiter, run_budget,
                mode="l10", as_of_date=as_of, event_id=bzz_event_id,
            )
        if task.slot == "team_b":
            return fetch_bzzoiro_history(
                away_id, home_id, rate_limiter, run_budget,
                mode="l10", as_of_date=as_of, event_id=bzz_event_id,
            )
        return fetch_bzzoiro_history(
            home_id, away_id, rate_limiter, run_budget,
            mode="h2h", as_of_date=as_of, event_id=bzz_event_id,
        )

    if task.provider == "bzzoiro-tennis":
        # Addressed by the fixture's own id, not by a player pair: one
        # /matches/{id}/h2h/ request serves all three slots, and at 95 calls a
        # day that is what makes the provider usable at all.
        bzz_match_id = task.event.source_ids.get("bzzoiro-tennis", "")
        ids = task.event.provider_team_ids.get("bzzoiro-tennis", {})
        as_of = task.event.start_time[:10]
        if task.slot == "team_a":
            return fetch_bzzoiro_tennis_history(
                bzz_match_id, ids.get("home", ""), rate_limiter, run_budget,
                mode="l10", as_of_date=as_of,
            )
        if task.slot == "team_b":
            return fetch_bzzoiro_tennis_history(
                bzz_match_id, ids.get("away", ""), rate_limiter, run_budget,
                mode="l10", as_of_date=as_of,
            )
        return fetch_bzzoiro_tennis_history(
            bzz_match_id, "", rate_limiter, run_budget, mode="h2h", as_of_date=as_of,
        )

    if task.provider == "sportdb":
        season = _season_label(task.event)
        args = (task.event.competition, season, run_budget)
        if task.slot == "team_a":
            return fetch_sportdb_history(team_a, team_b, *args, mode="l10", rate_limiter=rate_limiter)
        if task.slot == "team_b":
            return fetch_sportdb_history(team_b, team_a, *args, mode="l10", rate_limiter=rate_limiter)
        return fetch_sportdb_history(team_a, team_b, *args, mode="h2h", rate_limiter=rate_limiter)

    if task.slot == "team_a":
        return fetch_provider_team_metrics(task.provider, team_a, task.event.competition, rate_limiter)
    if task.slot == "team_b":
        return fetch_provider_team_metrics(task.provider, team_b, task.event.competition, rate_limiter)
    return fetch_provider_h2h_metrics(
        task.provider, team_a, team_b, rate_limiter, competition=task.event.competition
    )


def _build_tasks(event: EventRecord) -> list[_Task]:
    tasks = []
    for provider in PROVIDERS_BY_SPORT[event.sport]:
        tasks.append(_Task(event, "team_a", provider))
        tasks.append(_Task(event, "team_b", provider))
        tasks.append(_Task(event, "h2h", provider))

    # Providers addressed by native id rather than team name. Highlightly is
    # gated on discovery having captured its team ids for this exact event
    # (without them /statistics hard-fails, see providers.py); SportDB only
    # needs a competition name to page that league's season results.
    for provider in NATIVE_ID_PROVIDERS_BY_SPORT.get(event.sport, ()):
        if provider == "highlightly" and not event.provider_team_ids.get("highlightly"):
            continue
        if provider == "sportdb" and not event.competition:
            continue
        # Same gate as highlightly, one field wider: the l10 slots need the
        # native team ids and the h2h slot needs the native fixture id, and an
        # event discovered only by another source has neither.
        if provider == "bzzoiro" and not (
            event.provider_team_ids.get("bzzoiro") and event.source_ids.get("bzzoiro")
        ):
            continue
        # Tennis, same gate: the l10 slots need the native player ids and every
        # slot needs the native match id, because the listing hangs off the
        # fixture rather than off a player.
        if provider == "bzzoiro-tennis" and not (
            event.provider_team_ids.get("bzzoiro-tennis")
            and event.source_ids.get("bzzoiro-tennis")
        ):
            continue
        tasks.append(_Task(event, "team_a", provider))
        tasks.append(_Task(event, "team_b", provider))
        tasks.append(_Task(event, "h2h", provider))
    return tasks


def _compute_readiness(
    sport: Sport,
    metrics: dict[str, MetricObservation],
    has_player_metrics: bool = False,
) -> str:
    if not metrics:
        # Props alone are PARTIAL, not BLOCKED. BLOCKED means "no provider
        # returned any data", and ANALYZE drops a BLOCKED dossier whole -- so
        # calling this BLOCKED would silently discard the twenty calls' worth of
        # per-player history the run just paid for, on exactly the events where
        # the team metrics failed and a prop is the only read left.
        return "PARTIAL" if has_player_metrics else "BLOCKED"
    priority = PRIORITY_METRICS[sport]
    with_two_or_more = 0
    with_one_or_more = 0
    for name in priority:
        obs = metrics.get(name)
        if obs is None:
            continue
        providers = {pv.provider for pv in (*obs.team_a_l10, *obs.team_b_l10, *obs.h2h)}
        if len(providers) >= 2:
            with_two_or_more += 1
        if len(providers) >= 1:
            with_one_or_more += 1
    if with_two_or_more >= 3:
        return "READY"
    if with_one_or_more >= 1:
        return "PARTIAL"
    # Non-priority metrics have data but none of the 3 priority metrics do:
    # not "zero providers returned anything" (that's the literal BLOCKED
    # definition), so this falls through to PARTIAL rather than BLOCKED.
    return "PARTIAL"


# A fixture already under way cannot be backed pre-match, and one kicking off
# in three minutes will be off the board before its dossier is written, so the
# buffer treats both the same.
_KICKOFF_BUFFER = timedelta(minutes=5)


def _has_started(event: EventRecord, now: datetime) -> bool:
    """Whether ``event`` is past kickoff, or inside the pre-kickoff buffer.

    ``start_time`` is an offset-aware ISO string in EVENT_LIST_V1
    ("2026-08-25T16:10:00+00:00"); a naive one is read as UTC rather than
    raising on the comparison. An unparseable one counts as *not* started: a
    format we have not seen must not quietly demote every event at once.
    """
    try:
        parsed = datetime.fromisoformat(event.start_time)
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= now + _KICKOFF_BUFFER


def _dossier_for_event(
    event: EventRecord,
    buckets: dict[str, FetchOutcome],
    now: datetime | None = None,
    props: "_PlayerProps | None" = None,
) -> EventDossierV1:
    data_gaps: list[str] = []
    # Deprioritizing started events only helps when a cap is in force. Under a
    # generous cap, or none, they are enriched normally and reach the stats
    # sheet looking exactly like a bettable row, so the dossier has to say
    # otherwise -- the whole point of the cap fix is that these are not
    # backable pre-match.
    if now is not None and _has_started(event, now):
        data_gaps.append("kickoff already passed: not bettable pre-match")
    data_gaps.extend(f"team_a: {g}" for g in buckets["team_a"].data_gaps)
    data_gaps.extend(f"team_b: {g}" for g in buckets["team_b"].data_gaps)
    data_gaps.extend(f"h2h: {g}" for g in buckets["h2h"].data_gaps)

    all_names = set(buckets["team_a"].metrics) | set(buckets["team_b"].metrics) | set(buckets["h2h"].metrics)
    metrics = {
        name: MetricObservation(
            canonical_name=name,
            team_a_l10=buckets["team_a"].metrics.get(name, []),
            team_b_l10=buckets["team_b"].metrics.get(name, []),
            h2h=buckets["h2h"].metrics.get(name, []),
        )
        for name in all_names
    }
    team_a_name, team_b_name = _side_names(event)
    if props is not None:
        data_gaps.extend(f"player_props: {g}" for g in props.data_gaps)
    # Props can lift BLOCKED to PARTIAL (there *is* data) but never reach
    # READY: that tier means two independent providers agree on three priority
    # metrics, and one striker's shot history is neither.
    readiness = _compute_readiness(
        event.sport, metrics, bool(props is not None and props.observations)
    )
    if readiness == "BLOCKED":
        data_gaps.append("no provider returned any data for this event")
    return EventDossierV1(
        event_id=event.event_id,
        sport=event.sport,
        metrics=metrics,
        team_a_name=team_a_name or None,
        team_b_name=team_b_name or None,
        player_metrics=list(props.observations) if props is not None else [],
        lineup_status=props.lineup_status if props is not None else "",
        readiness=readiness,
        data_gaps=data_gaps,
    )



@dataclass
class _PlayerProps:
    """One event's player-prop observations, plus how they were obtained."""

    lineup_status: str = ""
    observations: list[PlayerMetricObservation] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


def _player_props_for_event(
    event: EventRecord, rate_limiter: RateLimiter, run_budget: RunBudget, last_n: int = 10
) -> _PlayerProps:
    """Collect per-player prop history for one event.

    Three steps, in this order because each depends on the last: read the XI (so
    we know whom to ask about), resolve each side's fixture dates (so a box score
    can be dated), then one call per outfield starter.

    Both a confirmed and a predicted XI are used -- ``lineup_status`` records
    which, and travels onto every row. Waiting for confirmation would mean no
    props until roughly an hour before kickoff, by which point the prices worth
    taking have moved; discarding the distinction instead would let a prop built
    on a guessed XI read exactly like one built on the announced XI. So the
    weaker premise is kept and labelled.

    Every failure is a data_gap. A missing lineup is the normal case for a
    fixture days out, not an error.
    """
    props = _PlayerProps()
    bzz_event_id = event.source_ids.get("bzzoiro", "")
    ids = event.provider_team_ids.get("bzzoiro", {})
    if not bzz_event_id:
        props.data_gaps.append("bzzoiro did not discover this event: no lineup to read")
        return props

    lineup_status, players_by_side, gaps = fetch_bzzoiro_lineup(
        bzz_event_id, rate_limiter, run_budget
    )
    props.lineup_status = lineup_status
    props.data_gaps.extend(gaps)
    if not players_by_side:
        return props

    as_of = event.start_time[:10]
    context: dict[str, tuple[str, str]] = {}
    for side in ("home", "away"):
        team_id = ids.get(side, "")
        if not team_id:
            continue
        side_context, context_gaps = fetch_bzzoiro_match_context(
            team_id, rate_limiter, run_budget, last_n=last_n, as_of_date=as_of
        )
        context.update(side_context)
        props.data_gaps.extend(context_gaps)

    tasks = [
        (side, player)
        for side in ("home", "away")
        for player in players_by_side.get(side, [])
        if str(player.get("position") or "") not in _SKIPPED_PROP_POSITIONS
    ]
    if not tasks:
        return props

    def _one(entry: tuple[str, dict]) -> tuple[str, dict, FetchOutcome]:
        side, player = entry
        return (
            side,
            player,
            fetch_bzzoiro_player_history(
                str(player["player_id"]),
                rate_limiter,
                run_budget,
                last_n=last_n,
                as_of_date=as_of,
                exclude_event_id=bzz_event_id,
                match_context=context,
            ),
        )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_one, entry) for entry in tasks]
        for future in as_completed(futures):
            try:
                side, player, outcome = future.result()
            except Exception as exc:  # noqa: BLE001 - one player must not abort the event
                props.data_gaps.append(f"player history unhandled error: {exc}")
                continue
            props.data_gaps.extend(outcome.data_gaps)
            for canonical_name, values in outcome.metrics.items():
                if not values:
                    continue
                props.observations.append(
                    PlayerMetricObservation(
                        player_id=str(player["player_id"]),
                        player_name=str(player["player_name"]),
                        team_side=side,
                        canonical_name=canonical_name,
                        l10=values,
                    )
                )
    return props


def _enrichment_priority(event: EventRecord, now: datetime) -> tuple[int, int, str]:
    """Order events best-corroborated-first, so a capped run spends its
    provider budget on the events most likely to reach READY: identity
    CONFIRMED by two sources beats a single-source FUZZY_MATCHED one, and an
    event whose Highlightly native ids were captured beats one without.

    Kickoff outranks corroboration. When no event is CONFIRMED and none carries
    native ids -- the normal case, every event FUZZY_MATCHED -- the
    corroboration term is the same constant for all of them and the sort
    collapses to "earliest kickoff wins", which is exactly backwards under a
    cap. On 2026-08-25 that sent three of five slots to K League fixtures whose
    kickoff was 86 minutes before the run finished, while Valencia - Real
    Betis, Bodo/Glimt - NEC and LASK - Celtic came back BLOCKED on the cap.

    Started events are pushed behind the cap rather than dropped from ACTIVE,
    so a run over a past date (a backfill or a re-analysis) still enriches
    everything it is given.
    """
    confirmed = 0 if event.identity_confidence == "CONFIRMED" else 1
    has_native_ids = 0 if event.provider_team_ids else 1
    return (
        1 if _has_started(event, now) else 0,
        confirmed + has_native_ids,
        event.start_time,
    )


def enrich_events(
    event_list: EventListV1,
    rate_limiter: RateLimiter | None = None,
    max_events: int | None = None,
    provider_call_budget: int = 100,
    player_props: bool = False,
) -> EventDossierListV1:
    """Enrich every ACTIVE event in ``event_list`` with raw statistics from
    every applicable provider. BLOCKED_IDENTITY events are carried through as
    BLOCKED placeholder dossiers so every EVENT_LIST_V1 event is accounted for.

    ``max_events`` caps how many ACTIVE events are enriched. A day's discovery
    routinely returns 150+ football fixtures and each one costs several dozen
    provider calls, which no provider quota survives; capping is what makes a
    real run finish inside budget. Events not enriched are reported as BLOCKED
    with an explicit reason rather than silently dropped.

    ``player_props`` adds one call per outfield starter (roughly 20 an event, on
    top of the ~30 the team metrics cost) and is off by default. It is opt-in
    rather than automatic because it roughly doubles a run's cost for a market
    surface that is only worth reading once a lineup exists -- which, for a
    fixture more than a few hours out, it does not.
    """
    rate_limiter = rate_limiter or RateLimiter()
    run_budget = RunBudget(limit=provider_call_budget)
    active_events = [e for e in event_list.events if e.status == "ACTIVE"]
    now = datetime.now(timezone.utc)

    skipped: list[EventRecord] = []
    if max_events is not None and len(active_events) > max_events:
        active_events.sort(key=lambda e: _enrichment_priority(e, now))
        active_events, skipped = active_events[:max_events], active_events[max_events:]

    per_event: dict[str, dict[str, FetchOutcome]] = {
        e.event_id: {"team_a": FetchOutcome(), "team_b": FetchOutcome(), "h2h": FetchOutcome()}
        for e in active_events
    }

    tasks = [task for event in active_events for task in _build_tasks(event)]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run_task, task, rate_limiter, run_budget): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:  # noqa: BLE001 - one (event, provider) failure must not abort the run
                outcome = FetchOutcome(data_gaps=[f"{task.provider}: unhandled error: {exc}"])
            per_event[task.event.event_id][task.slot].merge(outcome)

    # A second pass, not more tasks in the first: props need the fixture's XI
    # before they know which players to ask about, so they cannot be enumerated
    # up front alongside the team slots.
    props_by_event: dict[str, _PlayerProps] = {}
    if player_props and active_events:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_player_props_for_event, event, rate_limiter, run_budget): event
                for event in active_events
            }
            for future in as_completed(futures):
                event = futures[future]
                try:
                    props_by_event[event.event_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - one event's props must not abort the run
                    props_by_event[event.event_id] = _PlayerProps(
                        data_gaps=[f"unhandled error collecting player props: {exc}"]
                    )

    dossiers = [
        _dossier_for_event(
            event, per_event[event.event_id], now, props_by_event.get(event.event_id)
        )
        for event in active_events
    ]

    for event in event_list.events:
        if event.status == "BLOCKED_IDENTITY":
            dossiers.append(
                EventDossierV1(
                    event_id=event.event_id,
                    sport=event.sport,
                    metrics={},
                    readiness="BLOCKED",
                    data_gaps=[f"event blocked at discovery: {event.terminal_reason}"],
                )
            )

    for event in skipped:
        dossiers.append(
            EventDossierV1(
                event_id=event.event_id,
                sport=event.sport,
                metrics={},
                readiness="BLOCKED",
                data_gaps=[
                    f"not enriched: run capped at {max_events} events"
                    + (
                        " (kickoff already passed, deprioritized: not bettable pre-match)"
                        if _has_started(event, now)
                        else ""
                    )
                ],
            )
        )

    return EventDossierListV1(
        run_id=event_list.run_id,
        date=event_list.date,
        generated_at=_now_iso(),
        dossiers=dossiers,
    )
