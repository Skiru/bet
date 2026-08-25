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
from bet.simple_stats.contracts import EventListV1  # noqa: E402
from bet.simple_stats.enrich import enrich_events  # noqa: E402
from bet.simple_stats.persistence import default_db_path, persist_pipeline_run  # noqa: E402
from bet.simple_stats.preflight import enrich_preflight  # noqa: E402
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

    # ── Enrich ───────────────────────────────────────────────────────
    try:
        dossier_list = enrich_events(
            event_list,
            rate_limiter=rate_limiter,
            max_events=args.max_events,
            provider_call_budget=args.provider_call_budget,
        )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"enrichment crashed: {exc}", recoverable=False, run_id=run_id)
        _record(args, run_id, event_list.date, "FAILED", {"error": str(exc)}, started_at, str(exc))
        out.summary(verdict="FAILED", metrics={"total_dossiers": 0, "run_id": run_id})
        sys.exit(2)

    output_path = Path(args.output_dir) / f"{event_list.date}_event_dossiers.json"
    write_json_atomic(output_path, dossier_list.model_dump(mode="json"))
    digest = sha256_file(output_path)
    out.event("artifact_written", path=str(output_path), sha256=digest, dossiers=len(dossier_list.dossiers))

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
        "planned_events": planned,
        "recommended_max_events": preflight["recommended_max_events"],
        "two_provider_coverage_by_sport": preflight["coverage_by_sport"],
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
