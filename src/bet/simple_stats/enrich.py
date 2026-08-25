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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bet.api_clients.rate_limiter import RateLimiter

from bet.simple_stats.contracts import (
    PRIORITY_METRICS,
    EventDossierListV1,
    EventDossierV1,
    EventListV1,
    EventRecord,
    MetricObservation,
    Sport,
)
from bet.simple_stats.providers import (
    NATIVE_ID_PROVIDERS_BY_SPORT,
    PROVIDERS_BY_SPORT,
    FetchOutcome,
    RunBudget,
    fetch_highlightly_history,
    fetch_provider_h2h_metrics,
    fetch_provider_team_metrics,
    fetch_sportdb_history,
)

MAX_WORKERS = 4


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
        tasks.append(_Task(event, "team_a", provider))
        tasks.append(_Task(event, "team_b", provider))
        tasks.append(_Task(event, "h2h", provider))
    return tasks


def _compute_readiness(sport: Sport, metrics: dict[str, MetricObservation]) -> str:
    if not metrics:
        return "BLOCKED"
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
    event: EventRecord, buckets: dict[str, FetchOutcome], now: datetime | None = None
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
    readiness = _compute_readiness(event.sport, metrics)
    if readiness == "BLOCKED":
        data_gaps.append("no provider returned any data for this event")
    return EventDossierV1(
        event_id=event.event_id,
        sport=event.sport,
        metrics=metrics,
        readiness=readiness,
        data_gaps=data_gaps,
    )


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
) -> EventDossierListV1:
    """Enrich every ACTIVE event in ``event_list`` with raw statistics from
    every applicable provider. BLOCKED_IDENTITY events are carried through as
    BLOCKED placeholder dossiers so every EVENT_LIST_V1 event is accounted for.

    ``max_events`` caps how many ACTIVE events are enriched. A day's discovery
    routinely returns 150+ football fixtures and each one costs several dozen
    provider calls, which no provider quota survives; capping is what makes a
    real run finish inside budget. Events not enriched are reported as BLOCKED
    with an explicit reason rather than silently dropped.
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

    dossiers = [
        _dossier_for_event(event, per_event[event.event_id], now) for event in active_events
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
