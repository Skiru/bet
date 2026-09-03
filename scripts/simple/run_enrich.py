#!/usr/bin/env python3
"""ENRICH: fetch raw statistics for every DISCOVER event into EVENT_DOSSIER_V1[].

Usage:
    python3 scripts/simple/run_enrich.py --event-list PATH --output-dir PATH [-v]

Runs a provider-quota preflight first: ENRICH costs about a dozen provider
calls per event against daily quotas, so starting a run that cannot reach any
provider only burns time and produces an artifact of pure data_gaps. That case
exits PRECONDITION_FAILED before any network call.

Emits the repo-standard AGENT_SUMMARY:{json} contract via scripts/agent_output.py.
Exit codes: 0 = OK, 1 = PARTIAL, 2 = FAILED / PRECONDITION_FAILED.
"""
import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
scripts_path = str(ROOT / "scripts")
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.api_clients.rate_limiter import RateLimiter  # noqa: E402
from bet.simple_stats.artifact_io import sha256_file, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventDossierListV1,
    EventListV1,
    SuperbetOfferV1,
)
from bet.simple_stats.enrich import (  # noqa: E402
    SlateGate,
    build_slate_gate,
    enrich_events,
    gate_drop_kind,
)
from bet.simple_stats.providers import PRIMARY_PROVIDER_BY_SPORT  # noqa: E402
from bet.simple_stats.persistence import default_db_path, persist_pipeline_run  # noqa: E402
from bet.simple_stats.preflight import enrich_preflight  # noqa: E402
from bet.simple_stats.providers import espn_competition_coverage  # noqa: E402
from bet.simple_stats.run_context import record_run  # noqa: E402

STEP = "simple_stats:ENRICH"


def main() -> None:
    parser = argparse.ArgumentParser(description="ENRICH: simple_stats stat collection")
    parser.add_argument("--event-list", required=True, help="Path to EVENT_LIST_V1 JSON (from run_discover.py)")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--max-events",
        type=int,
        default=40,
        help="Max ACTIVE events to enrich, best-corroborated first (default: 40). "
             "A full day is 150+ fixtures, which exceeds every provider's daily quota.",
    )
    parser.add_argument(
        "--provider-call-budget",
        type=int,
        default=100,
        help="Per-provider call ceiling for this run (default: 100)",
    )
    parser.add_argument(
        "--player-props",
        action="store_true",
        help="Also collect per-player prop history (one call per outfield starter, "
             "~20 extra calls per event). Off by default: it roughly doubles a "
             "run's cost and needs a lineup, which a fixture days out has not got. "
             "Every prop row records whether the XI was confirmed or predicted.",
    )
    parser.add_argument(
        "--backfill-from",
        default=None,
        help="Path to an EVENT_DOSSIER_V1 artifact from an earlier run of the same "
             "day. Re-enriches only its BLOCKED and PARTIAL events and merges the "
             "result back into that same file, keeping its run_id. Worth doing now "
             "that bzzoiro's 7000/day makes a second pass able to add something: "
             "under highlightly's 100 it could not.",
    )
    parser.add_argument(
        "--superbet-offer",
        default=None,
        help="Path to the SUPERBET_OFFER_V1 artifact for this day. Turns on the "
             "third slate-gate rule: a fixture Superbet does not price, in a "
             "competition where it prices others, is not enriched. Without it "
             "the gate still applies its first two rules (the primary provider "
             "discovered the fixture; kickoff has not passed).",
    )
    parser.add_argument(
        "--no-slate-gate",
        action="store_true",
        help="Enrich every ACTIVE event, including ones no provider of record "
             "covers and ones already under way. For backfills and replays; a "
             "normal run wants the gate.",
    )
    parser.add_argument(
        "--now",
        default=None,
        help=(
            "Pin the clock the kickoff rules read (ISO 8601). For re-running a "
            "day and diffing it against its own earlier output; never use it on "
            "a live run."
        ),
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Run even if no provider has quota left (produces an all-gaps artifact)",
    )
    parser.add_argument(
        "--db-path", default=None, help=f"SQLite DB to persist into (default: {default_db_path()})"
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput(STEP, verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(timezone.utc).isoformat()

    event_list_path = Path(args.event_list)
    event_list = EventListV1.model_validate_json(event_list_path.read_text(encoding="utf-8"))
    run_id = event_list.run_id or "unknown"

    prior: EventDossierListV1 | None = None
    if args.backfill_from:
        prior = EventDossierListV1.model_validate_json(
            Path(args.backfill_from).read_text(encoding="utf-8")
        )
        if prior.date and event_list.date and prior.date != event_list.date:
            out.error(
                f"--backfill-from is for {prior.date}, not {event_list.date}: refusing to merge",
                recoverable=False,
            )
            out.summary(verdict="FAILED", metrics={"total_dossiers": 0, "run_id": run_id})
            sys.exit(2)
        # A fixture the slate gate refused is not incomplete, it is excluded --
        # retrying it spends the pass on events the gate will refuse again, and
        # (worse) on a backfill run without ``--superbet-offer`` the third rule
        # is not in force, so a fixture dropped for having no price would be
        # enriched after all. A fixture the *cap* skipped is a different matter
        # and is exactly what a backfill is for, so "capped" is retried.
        gate_refused = {
            dossier.event_id
            for dossier in prior.dossiers
            if any(
                (kind := gate_drop_kind(gap)) is not None and kind != "capped"
                for gap in dossier.data_gaps
            )
        }
        incomplete = {
            dossier.event_id
            for dossier in prior.dossiers
            if dossier.readiness in ("BLOCKED", "PARTIAL")
            and dossier.event_id not in gate_refused
        }
        # BLOCKED_IDENTITY events are dropped rather than retried: their problem
        # is that two sources disagree about what fixture this is, which no
        # amount of provider quota resolves.
        event_list = event_list.model_copy(
            update={
                "events": [
                    event
                    for event in event_list.events
                    if event.status == "ACTIVE" and event.event_id in incomplete
                ]
            }
        )
        # The prior run's own run_id, so the backfill lands in the same run
        # rather than inventing a second one for the same day.
        run_id = prior.run_id or run_id
        event_list = event_list.model_copy(update={"run_id": run_id})
        out.event(
            "backfill_scope",
            run_id=run_id,
            prior_artifact=str(args.backfill_from),
            incomplete_before=len(incomplete),
            gate_refused_not_retried=len(gate_refused),
            retryable_events=len(event_list.events),
        )

    out.event("run_start", run_id=run_id, date=event_list.date, events=len(event_list.events))

    # ── Preflight ────────────────────────────────────────────────────
    rate_limiter = RateLimiter()
    planned = min(args.max_events, sum(1 for e in event_list.events if e.status == "ACTIVE"))
    preflight = enrich_preflight(event_list, rate_limiter, planned_events=planned)
    for quota in preflight["quotas"]:
        out.event(
            "provider_quota",
            provider=quota["provider"],
            limit=quota["limit"],
            remaining=quota["remaining"],
            available=quota["available"],
            covers_events=quota.get("covers_events"),
        )
    for blocked in preflight["blocked"]:
        out.warning(f"provider unavailable: {blocked['reason']}", provider=blocked["provider"], kind=blocked["kind"])

    for thin in preflight["thin"]:
        out.warning(
            f"quota will run out mid-run: {thin['reason']}",
            provider=thin["provider"],
            covers_events=thin["covers_events"],
            planned_events=thin["planned_events"],
        )

    if preflight["verdict"] == "PRECONDITION_FAILED" and not args.skip_preflight:
        metrics = {
            "run_id": run_id,
            "date": event_list.date,
            "total_dossiers": 0,
            "usable_providers": preflight["usable_providers"],
            "blocked_providers": [b["provider"] for b in preflight["blocked"]],
            "preflight_reason": preflight["reason"],
        }
        out.error(f"preflight failed: {preflight['reason']}", recoverable=False)
        _record(args, run_id, event_list.date, "PRECONDITION_FAILED", metrics, started_at, preflight["reason"])
        out.summary(verdict="PRECONDITION_FAILED", metrics=metrics)
        sys.exit(2)

    out.event(
        "preflight_ok",
        usable_providers=preflight["usable_providers"],
        planned_events=planned,
        recommended_max_events=preflight["recommended_max_events"],
        coverage_by_sport=preflight["coverage_by_sport"],
    )

    # ── Slate gate ───────────────────────────────────────────────────
    gate: SlateGate | None = None
    if not args.no_slate_gate:
        offer: SuperbetOfferV1 | None = None
        if args.superbet_offer:
            offer_path = Path(args.superbet_offer)
            if offer_path.exists():
                try:
                    offer = SuperbetOfferV1.model_validate_json(
                        offer_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError) as exc:
                    # Fail towards the permissive gate, never towards an empty
                    # slate. An unreadable board is not evidence that the book
                    # prices nothing, and this is the step that spends the
                    # provider budget -- crashing here costs the whole run.
                    out.warning(
                        f"superbet offer unusable, gating without it: {exc}",
                        path=str(offer_path),
                    )
                    offer = None
                if offer is not None and offer.date and event_list.date and offer.date != event_list.date:
                    # Gating today's slate on yesterday's board would drop
                    # every fixture that is not a repeat, silently.
                    out.warning(
                        f"superbet offer is for {offer.date}, not {event_list.date}: "
                        "ignoring it for the slate gate",
                    )
                    offer = None
            else:
                out.warning(f"superbet offer not found, gating without it: {offer_path}")
        # A run over a past date is a backfill or a re-analysis, and there every
        # fixture has started. Enforcing kickoff would empty the slate rather
        # than protect it.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        enforce_kickoff = not event_list.date or event_list.date >= today
        gate = build_slate_gate(event_list, offer, enforce_kickoff=enforce_kickoff)
        out.event(
            "slate_gate",
            have_offer=gate.have_offer,
            enforce_kickoff=enforce_kickoff,
            priced_events=len(gate.priced_event_ids),
            priced_competitions=len(gate.priced_competitions),
        )

    # ── Enrich ───────────────────────────────────────────────────────
    try:
        dossier_list = enrich_events(
            event_list,
            rate_limiter=rate_limiter,
            max_events=args.max_events,
            provider_call_budget=args.provider_call_budget,
            player_props=args.player_props,
            slate_gate=gate,
        )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"enrichment crashed: {exc}", recoverable=False, run_id=run_id)
        _record(args, run_id, event_list.date, "FAILED", {"error": str(exc)}, started_at, str(exc))
        out.summary(verdict="FAILED", metrics={"total_dossiers": 0, "run_id": run_id})
        sys.exit(2)

    merged_count = 0
    if prior is not None:
        dossier_list, merged_count = _merge_dossiers(prior, dossier_list)
        # Rewritten in place: Filar F is explicit that a backfill joins the
        # existing run rather than producing a second artifact for the same day
        # that a reader then has to choose between.
        output_path = Path(args.backfill_from)
        out.event("backfill_merged", improved_dossiers=merged_count, path=str(output_path))
    else:
        output_path = Path(args.output_dir) / f"{event_list.date}_event_dossiers.json"
    write_json_atomic(output_path, dossier_list.model_dump(mode="json"))
    digest = sha256_file(output_path)
    out.event("artifact_written", path=str(output_path), sha256=digest, dossiers=len(dossier_list.dossiers))

    # What the gate refused, and what that cost. A slate that shrinks silently
    # is the thing the gate must never become: 3-6 fixtures a day sit in a
    # competition bzzoiro covers and are priced by Superbet, and bzzoiro's
    # /events/ simply did not return them (measured 2026-09-01/02). Those are
    # real bets the run is choosing not to make, so they are named, not counted.
    gate_drops: dict[str, int] = {}
    for dossier in dossier_list.dossiers:
        for gap in dossier.data_gaps:
            kind = gate_drop_kind(gap)
            if kind:
                gate_drops[kind] = gate_drops.get(kind, 0) + 1
    if gate_drops:
        out.event("slate_gate_drops", **gate_drops)
    if gate is not None and gate.have_offer:
        covered = {
            e.competition
            for e in event_list.events
            if e.sport in PRIMARY_PROVIDER_BY_SPORT
            and e.source_ids.get(PRIMARY_PROVIDER_BY_SPORT[e.sport])
        }
        missed = [
            e
            for e in event_list.events
            if e.status == "ACTIVE"
            and e.sport in PRIMARY_PROVIDER_BY_SPORT
            and not e.source_ids.get(PRIMARY_PROVIDER_BY_SPORT[e.sport])
            and e.competition in covered
            and e.event_id in gate.priced_event_ids
        ]
        for event in missed:
            out.warning(
                f"bettable fixture dropped for want of a {PRIMARY_PROVIDER_BY_SPORT[event.sport]} "
                f"id: {event.home_team} v {event.away_team} ({event.competition}) is priced by "
                f"Superbet and the provider covers this competition, but discovery captured no id",
                event_id=event.event_id,
            )
        if missed:
            out.event("primary_discovery_misses", count=len(missed))

    by_readiness = {"READY": 0, "PARTIAL": 0, "BLOCKED": 0}
    providers_seen: dict[str, int] = {}
    gap_count = 0
    total = len(dossier_list.dossiers)
    for index, dossier in enumerate(dossier_list.dossiers, start=1):
        by_readiness[dossier.readiness] = by_readiness.get(dossier.readiness, 0) + 1
        gap_count += len(dossier.data_gaps)
        for observation in dossier.metrics.values():
            for value in (*observation.team_a_l10, *observation.team_b_l10, *observation.h2h):
                providers_seen[value.provider] = providers_seen.get(value.provider, 0) + 1
        if args.verbose:
            out.progress(
                index,
                total,
                f"{dossier.event_id[:12]} {dossier.readiness} metrics={len(dossier.metrics)}",
            )

    persisted, persist_error = _persist(out, args, event_list, dossier_list)

    metrics = {
        "run_id": run_id,
        "date": event_list.date,
        "total_dossiers": total,
        "by_readiness": by_readiness,
        "observations_by_provider": providers_seen,
        "data_gap_count": gap_count,
        "usable_providers": preflight["usable_providers"],
        "blocked_providers": [b["provider"] for b in preflight["blocked"]],
        "max_events": args.max_events,
        "player_props": args.player_props,
        "player_prop_observations": sum(
            len(d.player_metrics) for d in dossier_list.dossiers
        ),
        "backfill_from": args.backfill_from,
        "backfill_improved_dossiers": merged_count if prior is not None else None,
        "planned_events": planned,
        "recommended_max_events": preflight["recommended_max_events"],
        # Renamed from "two_provider_coverage_by_sport" on 2026-09-03. For a
        # sport with a primary provider it has not counted two providers since
        # readiness stopped requiring them: it is the primary's own reach, which
        # is what bounds a readable slate.
        "slate_coverage_by_sport": preflight["coverage_by_sport"],
        "slate_gate_drops": gate_drops,
        # Drift signal for the ESPN competition table. It is exact-match, so an
        # unenumerated feed spelling costs a provider silently; measured once
        # on 2026-08-28 and invisible in every run since. Named here, with the
        # unresolved competitions listed, because each one is a single authored
        # table row away from being a second provider.
        "espn_competition_coverage": espn_competition_coverage(event_list.events),
        "quota_thin_providers": [t["provider"] for t in preflight["thin"]],
        "output_path": str(output_path),
        "output_sha256": digest,
        "persisted": persisted,
        "persist_error": persist_error,
    }

    if not total or by_readiness["BLOCKED"] == total:
        out.error("no event reached PARTIAL or better", recoverable=False)
        verdict = "FAILED"
    elif by_readiness["PARTIAL"] or by_readiness["BLOCKED"] or not persisted:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    _record(args, run_id, event_list.date, verdict, metrics, started_at, persist_error)
    out.summary(verdict=verdict, metrics=metrics)
    sys.exit(0 if verdict == "OK" else (1 if verdict == "PARTIAL" else 2))


_READINESS_RANK = {"BLOCKED": 0, "PARTIAL": 1, "READY": 2}


def _observation_count(dossier) -> int:
    return sum(
        len(o.team_a_l10) + len(o.team_b_l10) + len(o.h2h) for o in dossier.metrics.values()
    ) + sum(len(o.l10) for o in dossier.player_metrics)


def _merge_dossiers(prior, fresh) -> tuple[EventDossierListV1, int]:
    """Fold a backfill pass back into the artifact it was derived from.

    A re-run is not automatically an improvement: quota may have run out
    between the two passes, or a provider may have gone down, in which case the
    second attempt returns *less*. Replacing unconditionally would let a
    backfill destroy the data the first run paid for -- so a fresh dossier
    replaces the old one only when it reaches a better readiness, or the same
    readiness with strictly more observations behind it.

    Every event of the original artifact survives, in its original order: this
    file is the complete account of the day's slate, and an event that a
    backfill could not improve must still be in it.
    """
    fresh_by_id = {dossier.event_id: dossier for dossier in fresh.dossiers}
    merged = []
    improved = 0
    for old in prior.dossiers:
        new = fresh_by_id.get(old.event_id)
        if new is None:
            merged.append(old)
            continue
        old_key = (_READINESS_RANK.get(old.readiness, 0), _observation_count(old))
        new_key = (_READINESS_RANK.get(new.readiness, 0), _observation_count(new))
        if new_key > old_key:
            merged.append(new)
            improved += 1
        else:
            merged.append(old)
    return (
        EventDossierListV1(
            run_id=prior.run_id or fresh.run_id,
            date=prior.date or fresh.date,
            generated_at=fresh.generated_at,
            dossiers=merged,
        ),
        improved,
    )


def _persist(out: AgentOutput, args, event_list, dossier_list) -> tuple[bool, str | None]:
    try:
        persist_pipeline_run(
            event_list, dossier_list, None, betting_date=event_list.date, db_path=args.db_path
        )
        out.event("db_persisted", table="analysis_raw_data", dossiers=len(dossier_list.dossiers))
        return True, None
    except Exception as exc:
        out.error(f"DB persistence failed: {exc}", recoverable=True)
        return False, str(exc)


def _record(args, run_id: str, date: str, status: str, stats: dict, started_at: str, error: str | None) -> None:
    try:
        record_run(
            date=date,
            step="ENRICH",
            status=status,
            run_id=run_id,
            db_path=args.db_path,
            stats=stats,
            error_message=error,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never mask the run's own result
        print(f"[{STEP}] WARNING: could not record pipeline_runs row: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
