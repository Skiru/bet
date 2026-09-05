"""ENRICH: fetch raw statistics for every discovered event from all applicable
providers, combining (never falling back) across providers.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 1). (event, provider)
is one unit of work in ThreadPoolExecutor(max_workers=4), mirroring
src/bet/discovery/coordinator.py:_fetch_all_sources's ThreadPoolExecutor
idiom. Every task is wrapped so any exception (including SportDBMCPError and
subclasses) becomes a data_gaps entry, never an aborted run.
"""
from __future__ import annotations

from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from bet.api_clients.rate_limiter import RateLimiter

from bet.simple_stats.analyze import scope_values
from bet.simple_stats.contracts import (
    PRIORITY_METRICS,
    EventDossierListV1,
    EventDossierV1,
    EventListV1,
    EventRecord,
    MetricObservation,
    PlayerMetricObservation,
    ProviderValue,
    RefereeProfile,
    Sport,
    SquadAvailability,
    SuperbetOfferV1,
    TeamSeasonForm,
)
from bet.simple_stats.providers import (
    NATIVE_ID_PROVIDERS_BY_SPORT,
    PRIMARY_PROVIDER_BY_SPORT,
    PROVIDERS_BY_SPORT,
    FetchOutcome,
    MatchContext,
    RunBudget,
    corroborators_for,
    fetch_bzzoiro_history,
    fetch_bzzoiro_league_table,
    fetch_bzzoiro_lineup,
    fetch_bzzoiro_match_context,
    fetch_bzzoiro_player_history,
    fetch_bzzoiro_referee,
    fetch_bzzoiro_squad_availability,
    fetch_bzzoiro_team_league_id,
    fetch_highlightly_history,
    fetch_provider_h2h_metrics,
    fetch_provider_team_metrics,
    fetch_sportdb_history,
    metric_capable_providers,
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


def _has_primary_identity(event: EventRecord) -> bool:
    """Whether the sport's primary provider can be addressed for this event.

    The same two fields the primary's own slots are gated on below: the native
    team ids for the l10 lookups and the native fixture id for H2H.
    """
    primary = PRIMARY_PROVIDER_BY_SPORT.get(event.sport)
    if primary is None:
        return False
    return bool(event.provider_team_ids.get(primary) and event.source_ids.get(primary))


def _build_tasks(event: EventRecord) -> list[_Task]:
    # A corroborator is only scheduled where there is something to corroborate.
    #
    # Without this, espn-football was the *sole* source of 578 rows on
    # 2026-09-02 (82 of them in the top sheet) -- rows carrying six metrics from
    # a provider kept for its ability to check bzzoiro's fifty-five, on fixtures
    # bzzoiro had never seen. That is not a second opinion; it is a first
    # opinion from the weaker instrument, wearing the label of a second one.
    #
    # Belt and braces with the slate gate in ``enrich_events``: the gate stops
    # such fixtures being enriched at all on a normal run, and this stops them
    # producing single-source corroborator rows on a run where the gate is off
    # (--no-slate-gate, a backfill, a test).
    corroborators = set(corroborators_for(event.sport))
    skip_corroborators = bool(corroborators) and not _has_primary_identity(event)

    tasks = []
    for provider in PROVIDERS_BY_SPORT[event.sport]:
        if skip_corroborators and provider in corroborators:
            continue
        tasks.append(_Task(event, "team_a", provider))
        tasks.append(_Task(event, "team_b", provider))
        tasks.append(_Task(event, "h2h", provider))

    # Providers addressed by native id rather than team name. Highlightly is
    # gated on discovery having captured its team ids for this exact event
    # (without them /statistics hard-fails, see providers.py); SportDB only
    # needs a competition name to page that league's season results.
    for provider in NATIVE_ID_PROVIDERS_BY_SPORT.get(event.sport, ()):
        if skip_corroborators and provider in corroborators:
            continue
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
        tasks.append(_Task(event, "team_a", provider))
        tasks.append(_Task(event, "team_b", provider))
        tasks.append(_Task(event, "h2h", provider))
    return tasks


# How many distinct matches the primary provider must have served, on each
# side, for a priority metric to count as complete.
#
# Five, because five is the number ``bet_builder_draft.tier_for_row`` already
# treats as the floor of a usable sample (n<5 is WEAK, n<3 is DROP). Readiness
# that meant anything other than "this dossier can produce a row the tier
# system will accept" would be a second, quieter opinion about sample size.
#
# Measured against 2026-09-02: of the 52 football fixtures bzzoiro identified,
# 34 clear this bar on all three priority metrics. At six it is 20 and at eight
# it is 8 -- bzzoiro's scoped ``as_of_date`` window commonly returns five or six
# matches a side, so a higher bar would report a full sample as an incomplete
# one.
_READY_MIN_PRIMARY_MATCHES = 5


def _scoped_side(bucket: list[ProviderValue]) -> list[ProviderValue]:
    """One side's observations, minus the ones ANALYZE will refuse to count.

    ``readiness`` is a promise about the sample the operator is going to read,
    and until 2026-09-04 it was made about a different sample than the one that
    reaches the sheet. ENRICH counted every observation a provider returned;
    ANALYZE then put each per-team bucket through ``scope_values`` and threw out
    the pre-season friendlies and the previous season's matches. So the two
    disagreed about how much evidence a fixture had, and always in the same
    direction -- READY was measured on a sample that included matches nobody
    would price off.

    On the 2026-09-04 slate that gap was not academic. Stade Lavallois - Red
    Star reported ``corners_total`` 6/6 and cleared the floor, but two of
    Lavallois's six were July friendlies (US Granville, Stade Malherbe Caen);
    Ligue 2 had played four rounds, so the honest count was 4. Across the 22
    READY football dossiers ``PRE_SEASON_FRIENDLY`` fired 532 times on
    ``corners_total`` alone. The fixtures were not mislabelled by accident --
    they were labelled off evidence that had already been ruled inadmissible
    one step downstream.

    Scoped **per bucket**, never pooled, which is the rule
    ``analyze._rows_for_market`` states and for the same reason: a per-team
    sample is one bucket, so this team's own newest season is the right target
    for it, and pooling would let one side's cup run decide what counts as
    current for the other.

    ``surface`` and ``match_format`` are deliberately not passed. Both need the
    fixture's own pin, which is resolved from the competition name that only
    ANALYZE is given (``--event-list``), and both are tennis-only. Leaving them
    out means this filter applies exactly the two sport-neutral rules -- the
    competition pin and the stale season -- and a tennis dossier is never
    scored against a surface this function cannot see. It therefore removes at
    most what ANALYZE removes, never more.
    """
    kept, _ = scope_values(bucket)
    return kept


def _side_match_counts(
    providers: Collection[str],
    side_a: list[ProviderValue],
    side_b: list[ProviderValue],
) -> tuple[int, int]:
    """Distinct matches ``providers`` served for each team, for one metric.

    Distinct *matches*, not observations: bzzoiro reports a full-match total, a
    per-team total and both half-splits off the same fixture, so counting rows
    would report one match as four. Where ``providers`` holds more than one
    name the union is counted, for the same reason -- two providers reading the
    same fixture are one match of evidence, not two.

    Takes the two sides already scoped rather than the ``MetricObservation``,
    so the caller cannot count a bucket it forgot to put through
    ``_scoped_side`` -- the omission this signature exists to make impossible.
    """
    wanted = frozenset(providers)
    return tuple(  # type: ignore[return-value]
        len({pv.match_id for pv in bucket if pv.provider in wanted and pv.match_id})
        for bucket in (side_a, side_b)
    )


def _compute_readiness(
    sport: Sport,
    metrics: dict[str, MetricObservation],
    has_player_metrics: bool = False,
) -> str:
    """READY means the sport's primary provider covered this fixture.

    It used to mean "two providers covered it", which for football was a
    measurement of somebody else's league map. espn-football is the only
    provider that can be a second opinion on the majors, so 35 of the 36 READY
    dossiers of 2026-09-02 were READY because ESPN happened to know the
    competition -- and bzzoiro, which had served 55 metrics per match on every
    one of them, could not make a single fixture READY on its own. A quality
    label that a richer provider cannot earn is not measuring quality.

    So for a sport with a primary (PRIMARY_PROVIDER_BY_SPORT), READY asks the
    question the operator actually needs answered: did the source of record
    return a usable sample, on both sides, for all three priority metrics.
    Corroboration is still recorded -- per row, by ``cross_provider_agreement``,
    which is where a second opinion belongs -- and still raises the tier
    ceiling. It is no longer what makes a fixture readable.

    Sports with no primary (tennis: bzzoiro-tennis answers 402) keep the
    two-provider rule *for the metrics where a second provider can exist*, and
    substitute a sample-depth floor for the ones where it cannot.

    That exception is not a relaxation, it is the repair of an unreachable
    bar. Tennis's two providers are complementary rather than ranked, and only
    ``total_games`` is served by both -- espn-tennis reads the published set
    score and holds no aces or double faults at any price. So "3 priority
    metrics with 2+ providers" asked for 3 where the ceiling
    (``metric_capable_providers``) is 1, and **no tennis dossier could ever be
    READY**, on any slate, with every provider healthy. It was recorded as an
    accepted 0 in the source-consolidation plan rather than as the arithmetic
    contradiction it is.

    Where corroboration is impossible the second opinion is replaced, not
    waived: the sole provider must have served ``_READY_MIN_PRIMARY_MATCHES``
    distinct matches on *both* sides, the same floor the primary branch asks
    of bzzoiro. A metric one provider covers thinly is still not READY -- on
    the 2026-08-31 tennis dossiers this promotes the two fixtures with 7-10
    matches a side and leaves PARTIAL the one whose first player has no aces
    sample at all.
    """
    if not metrics:
        # Props alone are PARTIAL, not BLOCKED. BLOCKED means "no provider
        # returned any data", and ANALYZE drops a BLOCKED dossier whole -- so
        # calling this BLOCKED would silently discard the twenty calls' worth of
        # per-player history the run just paid for, on exactly the events where
        # the team metrics failed and a prop is the only read left.
        return "PARTIAL" if has_player_metrics else "BLOCKED"
    priority = PRIORITY_METRICS[sport]
    primary = PRIMARY_PROVIDER_BY_SPORT.get(sport)
    with_one_or_more = 0
    complete = 0
    for name in priority:
        obs = metrics.get(name)
        if obs is None:
            continue
        # Every count below is taken after the scope filter, including the
        # provider set: a provider whose only contribution to this metric was a
        # friendly has not corroborated anything the sheet will read, and
        # counting it as a second opinion would move the same overstatement
        # from the depth branch into the corroboration branch.
        scoped_a = _scoped_side(obs.team_a_l10)
        scoped_b = _scoped_side(obs.team_b_l10)
        providers = {
            pv.provider for pv in (*scoped_a, *scoped_b, *_scoped_side(obs.h2h))
        }
        if len(providers) >= 1:
            with_one_or_more += 1
        if primary:
            side_a, side_b = _side_match_counts((primary,), scoped_a, scoped_b)
            if min(side_a, side_b) >= _READY_MIN_PRIMARY_MATCHES:
                complete += 1
            continue
        if len(metric_capable_providers(sport, name)) >= 2:
            # A second opinion is available on this metric, so its absence is a
            # real gap and depth cannot stand in for it.
            if len(providers) >= 2:
                complete += 1
        elif providers:
            side_a, side_b = _side_match_counts(providers, scoped_a, scoped_b)
            if min(side_a, side_b) >= _READY_MIN_PRIMARY_MATCHES:
                complete += 1
    if complete >= len(priority):
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
    extras: "_FixtureExtras | None" = None,
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
    if extras is not None:
        data_gaps.extend(f"fixture_context: {g}" for g in extras.data_gaps)

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
        # Carried straight from EVENT_LIST at no request cost, so it is attached
        # even when every provider failed: knowing a BLOCKED fixture is a derby
        # on neutral ground is still worth more than knowing nothing about it.
        fixture_context=event.fixture_context,
        referee=extras.referee if extras is not None else None,
        squad_availability=list(extras.squad_availability) if extras is not None else [],
        season_form=list(extras.season_form) if extras is not None else [],
    )


@dataclass
class _FixtureExtras:
    """One event's circumstances: who referees it and who cannot play.

    Kept apart from ``_PlayerProps`` because the two answer different questions
    and fail independently. Props need a lineup and are opt-in; this needs only
    ids the event already carries, and is worth collecting on every football
    fixture -- ``readiness`` does not depend on it, so a failure here degrades
    the report rather than the run.

    **None of it is an observation.** These fields reach the dossier's context
    slots, never ``metrics``, so no hit rate can be counted from them.
    """

    referee: RefereeProfile | None = None
    squad_availability: list[SquadAvailability] = field(default_factory=list)
    season_form: list[TeamSeasonForm] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


def _fixture_extras_for_event(
    event: EventRecord,
    rate_limiter: RateLimiter,
    run_budget: RunBudget | None,
) -> _FixtureExtras:
    """Referee profile and both squads' absences for one football fixture.

    Roughly three requests an event, against a football product that is uncapped
    on this account -- and the referee half is usually free, since one official
    works several of a slate's fixtures and the profile cache is process-wide.

    Tennis is skipped outright: there is no referee endpoint on that product and
    its 100-a-day bucket is already the pipeline's one real quota constraint.
    """
    extras = _FixtureExtras()
    if event.sport != "football":
        return extras

    context = event.fixture_context
    if context is not None and context.referee_id:
        profile, gaps = fetch_bzzoiro_referee(context.referee_id, rate_limiter, run_budget)
        extras.data_gaps.extend(gaps)
        if profile:
            extras.referee = RefereeProfile(**profile)
    else:
        # Distinct from a failed/empty profile fetch above (that gap says
        # "referee profile for <id>"): this fixture never had a referee_id to
        # look up at all. Plan section 5a requires the two be told apart, not
        # folded into one 24/192-style number that could mean either "the
        # provider never names officials this early" or "the profile lookups
        # keep failing" -- they call for different fixes.
        extras.data_gaps.append("referee: no referee_id on this fixture")

    ids = event.provider_team_ids.get("bzzoiro", {})
    for side in ("home", "away"):
        team_id = ids.get(side, "")
        if not team_id:
            continue
        block, gaps = fetch_bzzoiro_squad_availability(
            team_id, side, rate_limiter, run_budget
        )
        extras.data_gaps.extend(gaps)
        if block:
            extras.squad_availability.append(SquadAvailability(**block))

    # league_id is bzzoiro-discovery-only (EventRecord.fixture_context is set
    # only when bzzoiro itself found the fixture, discover.py's
    # `_to_event_record`). Every other fixture with bzzoiro team ids -- most of
    # them, once name-matching has run -- still has a resolvable league: read
    # it off each side's own fixtures listing rather than leaving season_form
    # at 0 coverage for anything discover.py didn't source from bzzoiro.
    league_id = context.league_id if context is not None else None
    if not league_id and ids:
        as_of = event.start_time[:10]
        for team_id in (ids.get("home", ""), ids.get("away", "")):
            if not team_id:
                continue
            resolved, gaps = fetch_bzzoiro_team_league_id(
                team_id, as_of, rate_limiter, run_budget
            )
            extras.data_gaps.extend(gaps)
            if resolved:
                league_id = resolved
                break

    # One call per competition, not per fixture: a slate is dozens of matches
    # drawn from a handful of leagues, and the table is the same for all of
    # them. Both sides are read out of the one response.
    if league_id and ids:
        table, gaps = fetch_bzzoiro_league_table(
            league_id, rate_limiter, run_budget
        )
        extras.data_gaps.extend(gaps)
        for side in ("home", "away"):
            row = (table or {}).get(ids.get(side, ""))
            if not row:
                continue
            extras.season_form.append(
                TeamSeasonForm(
                    provider_team_id=row["provider_team_id"],
                    side=side,
                    team_name=row.get("team_name") or "",
                    group=row.get("group"),
                    position=row.get("position"),
                    played=row.get("played"),
                    points=row.get("points"),
                    xgf=row.get("xgf"),
                    xga=row.get("xga"),
                    xgd=row.get("xgd"),
                    xg_games=row.get("xg_games"),
                    form=row.get("form"),
                )
            )
    return extras


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
    context: dict[str, MatchContext] = {}
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


# The gate's three refusals, keyed for counting. The values are substrings of
# the sentences ``SlateGate.verdict`` returns and are asserted against them in
# ``test_every_gate_reason_has_a_kind`` -- a reason nobody can count is a slate
# that shrinks without a reported cause, which is the failure this whole gate
# exists to stop being invisible.
# Order matters: the first marker found wins, and the cap's own message can
# *contain* a gate phrase ("run capped at 30 events (kickoff already passed,
# deprioritized...)"). The cap is the operative fact there -- the event was
# never refused, it lost a ranking -- so it is tested first.
GATE_DROP_KINDS = {
    # Not a gate refusal at all: ``max_events`` ran out. It shares the "not
    # enriched: " prefix because it is the same kind of fact about the same
    # artifact, and it is counted separately because conflating "we chose not
    # to" with "we could not afford to" is how a shrinking slate stops being
    # readable. On the live 2026-09-03 run this was 13 of the 25 entries and
    # was reported as an unclassified gate drop.
    "capped": "run capped at",
    "no_primary_identity": "did not discover this fixture",
    "kickoff_passed": "kickoff already passed",
    "not_priced": "prices other fixtures of",
}
GATE_GAP_PREFIX = "not enriched: "


def gate_drop_kind(gap: str) -> str | None:
    """Which of the gate's refusals produced this ``data_gaps`` entry."""
    if not gap.startswith(GATE_GAP_PREFIX):
        return None
    for kind, marker in GATE_DROP_KINDS.items():
        if marker in gap:
            return kind
    return "other"


@dataclass(frozen=True)
class SlateGate:
    """Which fixtures are worth a provider call, and why the others are not.

    Three facts decide it, in this order, and each one is a fact rather than a
    preference:

    1. **The primary provider can be addressed.** For football that is bzzoiro.
       A fixture it never discovered has no per-team splits, no half-splits, no
       referee, no lineup and no player props -- 55 metrics missing against the
       6 a corroborator can supply. Measured on 2026-09-02: of 287 football
       fixtures, 235 were in this position and they produced 218 BLOCKED
       dossiers.
    2. **Kickoff has not passed.** A match under way cannot be backed pre-match.
       113 of that day's 325 dossiers were already past kickoff when ENRICH ran.
    3. **Superbet prices it.** bzzoiro's ~88 bookmakers do not include the only
       book the operator can actually bet into, so a fixture absent from that
       board is a sheet nobody can act on. 155 of the day's events had no offer.

    Rule 3 refuses rather than guesses, and that is the whole of its design.
    The offer is joined by name and kickoff, so a miss is indistinguishable from
    an absence *for one fixture* -- but not for a whole competition. If Superbet
    priced other fixtures of the same competition that day, this one's absence
    is real and the fixture is dropped; if it priced none of them, the silence
    is more likely ours than theirs and the fixture is kept. On 2026-09-02 that
    distinction is the difference between dropping Sint-Truidense - Union
    Saint-Gilloise (Belgian Pro League, no fixture of which Superbet matched at
    all -- a matcher miss) and dropping Atletico Nacional - Deportivo Cali
    (Copa Colombia, whose other fixture Superbet priced -- a real absence).
    """

    priced_event_ids: frozenset[str] = frozenset()
    # Keyed by (sport, competition), not by competition alone: the two sports
    # share this set and a bare name is not unique across them. Nothing has
    # collided yet -- it is cheap to make impossible rather than to watch for.
    priced_competitions: frozenset[tuple[str, str]] = frozenset()
    have_offer: bool = False
    enforce_kickoff: bool = True
    # When SUPERBET took the snapshot. Rule 3 can only speak about fixtures that
    # were still prematch at that moment -- see ``verdict``.
    offer_collected_at: datetime | None = None

    def verdict(self, event: EventRecord, now: datetime) -> str:
        """Why this event must not be enriched, or ``""`` to enrich it."""
        primary = PRIMARY_PROVIDER_BY_SPORT.get(event.sport)
        if primary and not _has_primary_identity(event):
            return (
                f"{primary} did not discover this fixture, so the source of "
                f"record cannot be addressed for it; a corroborator alone is "
                f"6 metrics against its 55"
            )
        if self.enforce_kickoff and _has_started(event, now):
            return "kickoff already passed: cannot be backed pre-match"
        if not self.have_offer or event.event_id in self.priced_event_ids:
            return ""
        # The book is read with ``offerState=prematch``, which stops carrying a
        # fixture the moment it goes live. So absence from the board says
        # nothing about pricing for anything that had already started when the
        # snapshot was taken -- and reading it as a refusal deletes precisely
        # the fixtures that were most worth having.
        #
        # Measured on the 2026-09-02 offer (collected 17:40 UTC): without this
        # clause the gate drops 19 of 38 US Open matches, every one of them
        # starting between 15:00 and 16:40 and every survivor starting after
        # 16:40. Ben Shelton - Hubert Hurkacz and Jessica Pegula - Sofia Kenin
        # were among the "unpriced". They were not unpriced; they were under
        # way. Rule 2 is the correct verdict for those, and it is already above.
        #
        # It also makes the gate safe against a stale offer: an old snapshot can
        # speak about fewer and fewer fixtures instead of deleting the slate.
        if self.offer_collected_at is not None and _has_started(
            event, self.offer_collected_at
        ):
            return ""
        if (event.sport, event.competition) in self.priced_competitions:
            return (
                f"Superbet prices other fixtures of '{event.competition}' today "
                f"but not this one: no price the operator can take"
            )
        # Superbet matched nothing at all in this competition, so its silence
        # is as likely to be our join failing as the book declining to price.
        return ""


def build_slate_gate(
    event_list: EventListV1,
    offer: SuperbetOfferV1 | None,
    *,
    enforce_kickoff: bool = True,
) -> SlateGate:
    """The gate for one day, from DISCOVER's event list and SUPERBET's offer.

    ``market_count``, not ``status``: an offer row carries the fixture's status
    inconsistently (on 2026-09-02, 82 FINISHED, 18 NOT_STARTED and 70 with no
    status at all) while a row with no markets is unambiguously not a price.
    All 84 rows that carried markets that day were unfinished.

    Note what an *empty* offer produces: no priced ids and no priced
    competitions, so rule 3 can never fire. A SUPERBET step that failed, ran
    before the board was posted, or matched nothing at all therefore cannot
    delete the slate -- it only stops contributing to it. That is the direction
    this has to fail in.
    """
    if offer is None:
        return SlateGate(have_offer=False, enforce_kickoff=enforce_kickoff)
    if offer.events_capped:
        # A board that was cut short cannot say a fixture is unpriced: the
        # fixtures it never looked at land in ``our_events_without_offer``
        # beside the genuine absences and are indistinguishable there. Rule 3
        # switches off rather than guessing. Measured on the live 2026-09-03
        # slate, a cap of 30 turned 9 priced fixtures into "not priced".
        return SlateGate(have_offer=False, enforce_kickoff=enforce_kickoff)
    try:
        collected_at: datetime | None = datetime.fromisoformat(offer.generated_at)
    except (TypeError, ValueError):
        collected_at = None
    if collected_at is not None and collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=timezone.utc)
    competition_of = {
        e.event_id: (e.sport, e.competition) for e in event_list.events if e.competition
    }
    priced = {
        row.event_id
        for row in offer.events
        if row.event_id and (row.market_count or 0) > 0
    }
    return SlateGate(
        priced_event_ids=frozenset(priced),
        priced_competitions=frozenset(
            competition_of[event_id] for event_id in priced if event_id in competition_of
        ),
        have_offer=True,
        enforce_kickoff=enforce_kickoff,
        offer_collected_at=collected_at,
    )


def _enrichment_priority(event: EventRecord, now: datetime) -> tuple[int, int, str]:
    """Order events best-corroborated-first, so a capped run spends its
    provider budget on the events most likely to reach READY: identity
    CONFIRMED by two sources beats a single-source FUZZY_MATCHED one, and an
    event whose native ids were captured beats one without. Football's are
    bzzoiro's since 2026-09-04 (highlightly no longer discovers football at
    all -- ``DISCOVERY_SOURCES_BY_SPORT``); this reads ``provider_team_ids``
    generically and does not care which source populated it.

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


def _apportion_cap(
    active_events: list[EventRecord],
    max_events: int,
    now: datetime,
    unconstrained_sports: frozenset[str] = frozenset(),
) -> tuple[list[EventRecord], list[EventRecord]]:
    """Split the cap between sports before ranking inside each one.

    One global ``_enrichment_priority`` sort looks fair and is not, because its
    tie-break rewards corroboration and corroboration is a property of the
    *sport*, not of the fixture. Football is discovered by three sources that
    routinely agree; tennis, on 2026-08-28, had 39 of 40 fixtures found by
    ``bzzoiro-tennis`` alone. So every tennis event scored worse than every
    football event, the single corroborated tennis fixture landed at position
    41 under ``--max-events 40``, and the sport vanished from the sheet -- while
    ``bzzoiro-tennis`` still held 72 unspent requests. Nothing reported this:
    the events came back BLOCKED with "run capped at 40 events", which reads
    like a quota problem rather than like a whole sport being sorted last.

    ``unconstrained_sports`` are exempt: they keep their whole slate and the
    cap is apportioned among the rest. The cap exists to ration a scarce daily
    quota, and a sport whose providers are not scarce has nothing to ration.
    Tennis is the case that forced this -- both its providers are effectively
    unlimited (tennis-abstract is a keyless scrape with no daily cap,
    espn-tennis allows 10,000 calls a day, about 3,300 events), yet the
    proportional split charged it for football's constraint: replayed against
    the 2026-09-02 slate (325 active events, cap 250) it dropped **9 of the 38
    tennis fixtures**, each of which could have been enriched at no quota cost
    whatsoever. Exempting them is not a widening of the run, it is declining to
    spend a budget on a sport that was never drawing on it.

    Every other sport therefore gets a share of the cap proportional to how much
    of the *constrained* slate it is, with at least one event whenever the cap
    has room, and ranks its own fixtures inside that share. A sport that cannot
    fill its share hands
    the remainder back, so a thin tennis day still spends its slots on football.
    """
    # Whole slates first, smallest sport first, for as long as they fit.
    #
    # Ascending order and a running budget, not a blanket exemption: bzzoiro is
    # uncapped too, so exempting every unconstrained sport outright would
    # delete the cap rather than aim it, and ``max_events`` has to keep meaning
    # something. Taking the smallest first is what makes the guarantee land
    # where it is needed -- tennis has never put more than 46 fixtures on a
    # board against a cap of 250, so it is always satisfied in full, while
    # football keeps whatever the cap has left and goes on being ranked inside
    # it exactly as before.
    exempt: list[EventRecord] = []
    if unconstrained_sports:
        sizes: dict[str, int] = {}
        for event in active_events:
            if event.sport in unconstrained_sports:
                sizes[event.sport] = sizes.get(event.sport, 0) + 1
        budget = max_events
        granted: set[str] = set()
        for sport in sorted(sizes, key=lambda s: (sizes[s], s)):
            if sizes[sport] <= budget:
                granted.add(sport)
                budget -= sizes[sport]
        if granted:
            exempt = [e for e in active_events if e.sport in granted]
            active_events = [e for e in active_events if e.sport not in granted]
            max_events = budget
    if not active_events:
        exempt.sort(key=lambda e: _enrichment_priority(e, now))
        return exempt, []
    max_events = max(max_events, 0)

    by_sport: dict[str, list[EventRecord]] = {}
    for event in active_events:
        by_sport.setdefault(event.sport, []).append(event)
    for events in by_sport.values():
        events.sort(key=lambda e: _enrichment_priority(e, now))

    # Largest-remainder apportionment, floor of one per sport that has events.
    total = len(active_events)
    quotas: dict[str, float] = {
        sport: len(events) * max_events / total for sport, events in by_sport.items()
    }
    shares = {sport: min(len(by_sport[sport]), int(quota)) for sport, quota in quotas.items()}
    if max_events >= len(by_sport):
        for sport in by_sport:
            shares[sport] = max(shares[sport], 1)
    # Hand out what rounding and the floor left over, largest remainder first,
    # then any slack a sport could not fill.
    for _ in range(2):
        remaining = max_events - sum(shares.values())
        if remaining <= 0:
            break
        for sport in sorted(by_sport, key=lambda s: quotas[s] - shares[s], reverse=True):
            if remaining <= 0:
                break
            room = len(by_sport[sport]) - shares[sport]
            take = min(room, remaining)
            shares[sport] += take
            remaining -= take
    # Trim if the floor pushed the total over the cap: give back from the sport
    # holding the most slots relative to its quota, never below one.
    while sum(shares.values()) > max_events:
        sport = max(shares, key=lambda s: shares[s] - quotas[s])
        if shares[sport] <= 1:
            break
        shares[sport] -= 1

    kept: list[EventRecord] = list(exempt)
    skipped: list[EventRecord] = []
    for sport, events in by_sport.items():
        share = shares[sport]
        kept.extend(events[:share])
        skipped.extend(events[share:])
    kept.sort(key=lambda e: _enrichment_priority(e, now))
    return kept, skipped


def enrich_events(
    event_list: EventListV1,
    rate_limiter: RateLimiter | None = None,
    max_events: int | None = None,
    provider_call_budget: int = 100,
    player_props: bool = False,
    slate_gate: SlateGate | None = None,
    now: datetime | None = None,
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

    ``now`` is the clock the kickoff rules read, and it is an argument for the
    same reason ``build_coupons``'s ``not_before`` and
    ``compare_sheet_to_offer``'s ``generated_at`` are: a step that reads
    ``datetime.now()`` internally cannot be re-run and diffed against its own
    earlier output. Re-running a day hours later otherwise drops every fixture
    that kicked off in between, and the diff then mixes a code change with the
    clock. Defaults to now, so a live run is unchanged.

    ``slate_gate`` decides which ACTIVE events are worth spending calls on at
    all; see :class:`SlateGate`. Passing None enriches everything, which is what
    a backfill or a replay of a finished day wants. It is not the same thing as
    ``max_events``: the cap answers "how many can we afford", the gate answers
    "which of these can produce a bet", and a run that spends its whole cap on
    fixtures the operator cannot back is inside budget and still wasted.
    """
    rate_limiter = rate_limiter or RateLimiter()
    run_budget = RunBudget(limit=provider_call_budget)
    active_events = [e for e in event_list.events if e.status == "ACTIVE"]
    now = now or datetime.now(timezone.utc)

    # Gate before cap, never after. The cap ranks what is left, so gating
    # second would let fixtures nobody can bet consume slots and then be
    # dropped -- the cap would bind on a slate the gate was about to shrink.
    gated: list[tuple[EventRecord, str]] = []
    if slate_gate is not None:
        kept: list[EventRecord] = []
        for event in active_events:
            reason = slate_gate.verdict(event, now)
            if reason:
                gated.append((event, reason))
            else:
                kept.append(event)
        active_events = kept

    skipped: list[EventRecord] = []
    if max_events is not None and len(active_events) > max_events:
        # Which sports are actually drawing on a scarce quota is a question for
        # the rate limiter, not a constant here -- see
        # ``preflight.sports_within_quota``. Resolved at the call site so a
        # replay that hands in a fake limiter gets the same answer its limiter
        # implies, rather than today's live quota.
        from bet.simple_stats.preflight import sports_within_quota

        active_events, skipped = _apportion_cap(
            active_events,
            max_events,
            now,
            unconstrained_sports=sports_within_quota(event_list, rate_limiter),
        )

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

    # Always collected, never opt-in. Unlike player props this needs no lineup
    # and no extra identity: the referee id arrived free with discovery and the
    # team ids are the same ones the metric fetches already used. Its failures
    # are data gaps, so a provider outage here costs a context line, not a run.
    extras_by_event: dict[str, _FixtureExtras] = {}
    if active_events:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_fixture_extras_for_event, event, rate_limiter, run_budget): event
                for event in active_events
            }
            for future in as_completed(futures):
                event = futures[future]
                try:
                    extras_by_event[event.event_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - one event must not abort the run
                    extras_by_event[event.event_id] = _FixtureExtras(
                        data_gaps=[f"unhandled error collecting fixture context: {exc}"]
                    )

    dossiers = [
        _dossier_for_event(
            event,
            per_event[event.event_id],
            now,
            props_by_event.get(event.event_id),
            extras_by_event.get(event.event_id),
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

    for event, reason in gated:
        dossiers.append(
            EventDossierV1(
                event_id=event.event_id,
                sport=event.sport,
                metrics={},
                readiness="BLOCKED",
                data_gaps=[f"not enriched: {reason}"],
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
